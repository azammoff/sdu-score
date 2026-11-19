from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import settings
from app.db.session import engine
from app.errors import register_exception_handlers
from app.routers import faculties, matches, players, stats, teams, tournaments


DESCRIPTION = """
Backend for **SDU Score**, the site that follows SDU's inter-faculty football tournaments:
teams and rosters, fixtures, live goals and cards, league tables and top scorers.

* Data is stored in PostgreSQL (`DATABASE_URL`); the schema is managed with Alembic.
* Read endpoints are public.
* Write endpoints need the admin key: click **Authorize** and enter the `X-API-Key`
  (default `sdu-admin-key`, set `ADMIN_API_KEY` to change it).
"""

app = FastAPI(title=settings.app_name, version="1.0.0", description=DESCRIPTION)
register_exception_handlers(app)

for module in (faculties, teams, players, tournaments, matches, stats):
    app.include_router(module.router)


STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def website():
    """The SDU Score website (plain HTML/CSS/JS that calls this API)."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", tags=["Meta"])
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "unavailable"
    return {"status": "ok" if database == "ok" else "degraded", "database": database}
