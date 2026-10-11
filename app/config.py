"""Runtime configuration read from environment variables."""
import os

from sqlalchemy.engine import URL


def database_url() -> str | URL:
    """Return the SQLAlchemy URL: Cloud SQL (Postgres) on Cloud Run, SQLite locally."""
    instance = os.getenv("INSTANCE_CONNECTION_NAME")
    if instance:
        return URL.create(
            "postgresql+pg8000",
            username=os.getenv("DB_USER", "moodbrew"),
            password=os.getenv("DB_PASS", ""),
            database=os.getenv("DB_NAME", "moodbrew"),
            query={"unix_sock": f"/cloudsql/{instance}/.s.PGSQL.5432"},
        )
    return os.getenv("DATABASE_URL", "sqlite:///./moodbrew.db")


GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
BARISTAS = max(1, int(os.getenv("BARISTAS", "2")))
QUEUE_WINDOW_MIN = 20
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "120"))
