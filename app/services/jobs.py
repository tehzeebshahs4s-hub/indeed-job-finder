from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Favorite, Job
from app.scraper.base import RawJob


def search_jobs_db(
    db: Session, keyword: str, location: str, page: int, per_page: int = 10
) -> tuple[list[Job], int]:
    """Search pre-scraped jobs in the DB (instant, no live scraping)."""
    q = db.query(Job)
    kw = keyword.strip().lower()
    loc = location.strip().lower()
    if kw:
        q = q.filter(
            (Job.title.ilike(f"%{kw}%"))
            | (Job.company.ilike(f"%{kw}%"))
            | (Job.summary.ilike(f"%{kw}%"))
        )
    if loc:
        q = q.filter(Job.location.ilike(f"%{loc}%"))
    total = q.count()
    jobs = q.order_by(Job.first_seen_at.desc()).offset(page * per_page).limit(per_page).all()
    return jobs, total


def upsert_jobs(db: Session, raw_jobs: list[RawJob]) -> list[Job]:
    """Insert or update Job rows for the given raw jobs; return ORM objects in order."""
    now = datetime.now(timezone.utc)
    result: list[Job] = []
    for raw in raw_jobs:
        job = (
            db.query(Job)
            .filter(Job.source == raw.source, Job.source_key == raw.source_key)
            .first()
        )
        if job is None:
            job = Job(
                source=raw.source,
                source_key=raw.source_key,
                title=raw.title,
                company=raw.company,
                location=raw.location,
                salary=raw.salary,
                summary=raw.summary,
                description=raw.description,
                url=raw.url,
                posted_at=raw.posted_at,
                first_seen_at=now,
                last_scraped_at=now,
            )
            db.add(job)
        else:
            job.title = raw.title
            job.company = raw.company
            job.location = raw.location
            job.salary = raw.salary or job.salary
            job.summary = raw.summary or job.summary
            job.description = raw.description or job.description
            job.url = raw.url or job.url
            job.posted_at = raw.posted_at or job.posted_at
            job.last_scraped_at = now
        result.append(job)
    db.commit()
    for job in result:
        db.refresh(job)
    return result


def get_job(db: Session, job_id: int) -> Job | None:
    return db.get(Job, job_id)


def favorite_ids_for_user(db: Session, user_id: int) -> set[int]:
    rows = db.execute(
        select(Favorite.job_id).where(Favorite.user_id == user_id)
    ).scalars().all()
    return set(rows)


def is_favorite(db: Session, user_id: int, job_id: int) -> bool:
    return (
        db.query(Favorite)
        .filter(Favorite.user_id == user_id, Favorite.job_id == job_id)
        .first()
        is not None
    )


def add_favorite(db: Session, user_id: int, job_id: int) -> bool:
    if is_favorite(db, user_id, job_id):
        return False
    db.add(Favorite(user_id=user_id, job_id=job_id))
    db.commit()
    return True


def remove_favorite(db: Session, user_id: int, job_id: int) -> bool:
    row = (
        db.query(Favorite)
        .filter(Favorite.user_id == user_id, Favorite.job_id == job_id)
        .first()
    )
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True
