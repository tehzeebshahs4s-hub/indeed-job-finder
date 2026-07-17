from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.database import init_db
from app.ratelimit import limiter
from app.routers import auth as auth_router
from app.routers import dashboard as dashboard_router
from app.routers import favorites as favorites_router
from app.routers import jobs as jobs_router
from app.routers import pages as pages_router
from app.templating import templates

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Indeed Jobs Aggregator",
    version="0.1.0",
    debug=settings.app_debug,
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth_router.router)
app.include_router(pages_router.router)
app.include_router(jobs_router.router)
app.include_router(favorites_router.router)
app.include_router(dashboard_router.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}
