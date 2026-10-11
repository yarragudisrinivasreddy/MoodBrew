"""MoodBrew API: vibe game, recommendations, wait times, staff room pulse."""
import re
import time
from collections import Counter, defaultdict, deque
from datetime import timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select

from . import queueing, vibes
from .config import BARISTAS, RATE_LIMIT_PER_MIN, QUEUE_WINDOW_MIN, database_url
from .db import Database, MenuItem, Order, VibeSession, utcnow
from .gemini import GeminiPicker
from .recommend import Picker, recommend

STATIC = Path(__file__).resolve().parent.parent / "static"
LABEL_RE = re.compile(r"^[A-Za-z0-9 -]{1,12}$")
CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net 'wasm-unsafe-eval'; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; "
    "img-src 'self' data: blob:; media-src 'self' blob:; "
    "connect-src 'self' https://cdn.jsdelivr.net https://storage.googleapis.com; "
    "worker-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
)


def _check_table(value: str | None) -> str | None:
    """Accept only short alphanumeric table labels."""
    if value in (None, ""):
        return None
    if not LABEL_RE.match(value):
        raise ValueError("invalid table label")
    return value


class VibeIn(BaseModel):
    """Expression scores computed on the device. Never contains an image."""

    client_id: str = Field(min_length=8, max_length=40, pattern=r"^[A-Za-z0-9-]+$")
    table: str | None = None
    joy: float = Field(0, ge=0, le=1)
    surprise: float = Field(0, ge=0, le=1)
    calm: float = Field(0, ge=0, le=1)
    play: float = Field(0, ge=0, le=1)

    _table = field_validator("table")(_check_table)


class OrderIn(BaseModel):
    """Items to order."""

    table: str | None = None
    item_ids: list[str] = Field(min_length=1, max_length=6)

    _table = field_validator("table")(_check_table)


def create_app(db_url=None, picker: Picker | None = None) -> FastAPI:
    """Application factory (tests inject an in-memory DB and a fake picker)."""
    database = Database(db_url or database_url())
    database.init()
    gemini = picker if picker is not None else GeminiPicker()
    app = FastAPI(title="MoodBrew", docs_url=None, redoc_url=None)
    hits: dict[str, deque] = defaultdict(deque)

    def get_db():
        with database.session() as session:
            yield session

    @app.middleware("http")
    async def guard(request: Request, call_next):
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window = hits[ip]
        while window and now - window[0] > 60:
            window.popleft()
        if request.url.path.startswith("/api") and len(window) >= RATE_LIMIT_PER_MIN:
            return JSONResponse({"detail": "Too many requests"}, status_code=429)
        window.append(now)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        return response

    def menu_dicts(db) -> list[dict]:
        rows = db.scalars(select(MenuItem)).all()
        return [
            {"id": r.id, "name": r.name, "kind": r.kind, "price": r.price,
             "prep_min": r.prep_min, "vibes": r.vibes, "blurb": r.blurb}
            for r in rows
        ]

    def current_load(db) -> float:
        since = utcnow() - timedelta(minutes=QUEUE_WINDOW_MIN)
        rows = db.execute(select(Order.load_min, Order.created_at).where(Order.created_at >= since)).all()
        return queueing.decayed_load([(r[0], r[1]) for r in rows], utcnow())

    @app.get("/api/health")
    def health():
        return {"status": "ok", "gemini": bool(getattr(gemini, "enabled", False))}

    @app.get("/api/menu")
    def menu(db=Depends(get_db)):
        return menu_dicts(db)

    @app.post("/api/vibe")
    def vibe(body: VibeIn, db=Depends(get_db)):
        scores = {k: getattr(body, k) for k in vibes.SCORE_KEYS}
        previous = db.scalar(select(func.count()).select_from(VibeSession).where(
            VibeSession.client_id == body.client_id)) or 0
        result_vibe = vibes.classify(scores)
        total = vibes.points(scores, previous)
        db.add(VibeSession(client_id=body.client_id, table_label=body.table, vibe=result_vibe,
                           points=total, total_score=sum(scores.values())))
        pick = recommend(menu_dicts(db), result_vibe, scores, gemini)
        return {"vibe": result_vibe, "points": total, "badge": vibes.badge(total),
                "returning_bonus": 25 * min(previous, 4), **pick}

    @app.post("/api/order")
    def order(body: OrderIn, db=Depends(get_db)):
        items = {i["id"]: i for i in menu_dicts(db)}
        if any(i not in items for i in body.item_ids):
            raise HTTPException(status_code=422, detail="Unknown menu item")
        own = float(sum(items[i]["prep_min"] for i in body.item_ids))
        eta = queueing.eta_minutes(current_load(db), own)
        db.add(Order(table_label=body.table, item_ids=body.item_ids, load_min=own))
        return {"eta_minutes": eta, "total": sum(items[i]["price"] for i in body.item_ids)}

    @app.get("/api/wait")
    def wait(db=Depends(get_db)):
        minutes = queueing.eta_minutes(current_load(db), 0)
        return {"wait_minutes": minutes, "status": queueing.busy_label(minutes), "baristas": BARISTAS}

    @app.get("/api/room")
    def room(db=Depends(get_db)):
        since = utcnow() - timedelta(minutes=60)
        counts = Counter(db.scalars(select(VibeSession.vibe).where(VibeSession.created_at >= since)).all())
        total = sum(counts.values())
        mix = {v: (round(100 * counts[v] / total) if total else 0) for v in vibes.VIBES}
        dominant = max(vibes.VIBES, key=lambda v: (counts[v], -vibes.VIBES.index(v))) if total else None
        minutes = queueing.eta_minutes(current_load(db), 0)
        return {"guests_last_hour": total, "mix": mix, "dominant": dominant,
                "tip": queueing.STAFF_TIPS.get(dominant, "No guests yet. Room is quiet."),
                "wait_minutes": minutes, "status": queueing.busy_label(minutes)}

    @app.get("/api/leaderboard")
    def leaderboard(db=Depends(get_db)):
        since = utcnow() - timedelta(hours=24)
        rows = db.execute(
            select(VibeSession.table_label, func.max(VibeSession.points).label("best"))
            .where(VibeSession.created_at >= since, VibeSession.table_label.is_not(None))
            .group_by(VibeSession.table_label).order_by(func.max(VibeSession.points).desc()).limit(5)
        ).all()
        return [{"table": r[0], "points": r[1]} for r in rows]

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/staff")
    def staff():
        return FileResponse(STATIC / "staff.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
