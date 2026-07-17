import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Use an isolated test DB before importing app modules.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("JWT_SECRET", "test-secret")

from fastapi.testclient import TestClient

import app.routers.jobs as jobs_router
from app.database import SessionLocal, init_db
from app.main import app
from app.scraper.base import FetchResult, RawJob


@pytest.fixture(scope="session")
def db_setup():
    init_db()
    yield


@pytest.fixture()
def client(db_setup, monkeypatch):
    """Test client with a deterministic fake job source."""
    monkeypatch.setattr(jobs_router.source_router, "fetch_jobs", _fake_fetch)
    with TestClient(app) as c:
        yield c
    # wipe data between tests
    db = SessionLocal()
    from app.models import Favorite, Job, SavedSearch, User

    for model in (Favorite, SavedSearch, Job, User):
        db.query(model).delete()
    db.commit()
    db.close()


def _fake_fetch(db, keyword, location, page, **kw):
    return FetchResult(
        source="indeed", total=1, page=page,
        jobs=[
            RawJob(
                source="indeed", source_key=f"{keyword}-{page}",
                title=f"{keyword} Developer",
                company="TestCo", location=location or "Remote",
                salary="$100,000", summary="Great role.", url="https://example.com",
                posted_at=datetime.now(timezone.utc),
            )
        ],
    )
