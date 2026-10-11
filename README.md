# MoodBrew: the face-off café companion

**Chosen challenge:** The Café Companion (Google Cloud Builder Pop-Up).

A guest scans the QR code on their table, plays a 10-second "pull a face" game, and gets a drink and snack picked for their vibe. Staff see an anonymous live read of the room.

## How it maps to the brief

| Brief theme | Feature | Where |
|---|---|---|
| Smarter Ordering | Vibe-aware pick, one tap to send drink and snack to the bar | `POST /api/vibe`, `POST /api/order`, `app/recommend.py` |
| Better Waits | Time-decayed queue model gives order ETA and bar status | `GET /api/wait`, `app/queueing.py` |
| Discovery | Gemini chooses from a shortlist built from the real menu and writes a witty line | `app/gemini.py`, `app/recommend.py` |
| Connect People | Table duel leaderboard, scan a different table's QR to challenge it | `GET /api/leaderboard` |
| Understand the Room | Staff pulse: vibe mix, wait, and a suggested move (`/staff`) | `GET /api/room`, `static/staff.html` |

## Approach and logic

**Gemini interprets, the rules compute.**

1. The camera is read **on the device** with MediaPipe Face Landmarker (blendshapes: smile, brow raise, jaw open, wink). Only four numbers (`joy, surprise, calm, play`) are sent to the server. No image, video or identity is stored or transmitted.
2. `app/vibes.py` deterministically turns those scores into a vibe: Spark, Zen, Cozy or Chaos, plus points and a badge.
3. `app/recommend.py` shortlists menu items per vibe. Gemini may only choose from that shortlist; its output is validated (known ids, correct kinds, line length) and the system falls back to rules if it is invalid or unavailable.
4. Orders feed a time-decayed queue model so waits reflect real load.
5. Guests who can't or don't want to use the camera pick a vibe by tapping.

## Google technology

- **Gemini** (`gemini-2.5-flash` via Vertex AI on Cloud Run, or API key locally) for picks and copy
- **Cloud Run** to host the app
- **Cloud SQL (PostgreSQL)** for menu, game sessions and orders (SQLite locally)
- **MediaPipe Face Landmarker** for on-device expression reading

## Security and privacy

- Face data never leaves the phone; the server stores scores only.
- Strict CSP, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` (camera on this origin only), no inline scripts or styles.
- Pydantic validation on every input (ranges, id formats, table labels), SQLAlchemy parameterised queries, per-IP rate limiting, non-root container.
- No secrets in the repo; the database password comes from environment variables or Secret Manager.

## Accessibility

- Full no-camera mode (tap a vibe), skip link, landmarks, visible focus, `aria-live` status for each round, 52px touch targets.
- Respects `prefers-reduced-motion`; high contrast on a dark palette.

## Run locally

```bash
pip install -r requirements-dev.txt
pytest
uvicorn app.main:create_app --factory --reload   # http://localhost:8000/?t=7
```

Optional: `export GEMINI_API_KEY=...` for Gemini picks. Without it the rules-based pick is used.

## Assumptions

- The QR code at each table points to `https://<service-url>/?t=<table number>`.
- Two baristas by default (`BARISTAS` env var).
- Vibe from expressions is a playful heuristic, never a judgement about the guest.
- Menu and prices (₹) are seed data in `app/menu_seed.py`.
