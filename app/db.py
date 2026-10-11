"""Database layer: Cloud SQL (Postgres) in production, SQLite locally and in tests."""
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import JSON, DateTime, Float, Integer, String, create_engine, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from .menu_seed import MENU


def utcnow() -> datetime:
    """Naive UTC timestamp (works identically on SQLite and Postgres)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    """Declarative base."""


class MenuItem(Base):
    """A drink or snack on the menu."""

    __tablename__ = "menu_items"
    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(8))
    price: Mapped[int] = mapped_column(Integer)
    prep_min: Mapped[int] = mapped_column(Integer)
    vibes: Mapped[list] = mapped_column(JSON)
    blurb: Mapped[str] = mapped_column(String(160))


class VibeSession(Base):
    """One finished game round. Stores scores only, never any image."""

    __tablename__ = "vibe_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[str] = mapped_column(String(40), index=True)
    table_label: Mapped[str | None] = mapped_column(String(12), nullable=True)
    vibe: Mapped[str] = mapped_column(String(8))
    points: Mapped[int] = mapped_column(Integer)
    total_score: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Order(Base):
    """A placed order."""

    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_label: Mapped[str | None] = mapped_column(String(12), nullable=True)
    item_ids: Mapped[list] = mapped_column(JSON)
    load_min: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Database:
    """Owns the engine and hands out short-lived sessions."""

    def __init__(self, url: str | URL) -> None:
        kwargs: dict = {"pool_pre_ping": True}
        if str(url).startswith("sqlite"):
            kwargs = {"connect_args": {"check_same_thread": False}}
            if str(url) in ("sqlite://", "sqlite:///:memory:"):
                kwargs["poolclass"] = StaticPool
        self.engine = create_engine(url, **kwargs)
        self._factory = sessionmaker(self.engine, expire_on_commit=False)

    def init(self) -> None:
        """Create tables and seed the menu once."""
        Base.metadata.create_all(self.engine)
        with self.session() as db:
            if db.scalar(select(MenuItem.id).limit(1)) is None:
                db.add_all(
                    MenuItem(id=i, name=n, kind=k, price=p, prep_min=m, vibes=v, blurb=b)
                    for i, n, k, p, m, v, b in MENU
                )

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Transactional session scope."""
        db = self._factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
