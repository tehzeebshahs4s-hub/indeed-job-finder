from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Application, Favorite, Job
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


# ---- Application tracking ----------------------------------------------------

APP_STATUSES = ["bookmarked", "applied", "interview", "offer", "rejected"]


def get_or_create_application(db: Session, user_id: int, job_id: int) -> Application:
    app = (
        db.query(Application)
        .filter(Application.user_id == user_id, Application.job_id == job_id)
        .first()
    )
    if app is None:
        app = Application(user_id=user_id, job_id=job_id, status="bookmarked")
        db.add(app)
        db.commit()
        db.refresh(app)
    return app


def update_application_status(
    db: Session, user_id: int, job_id: int, status: str, notes: str | None = None
) -> Application:
    app = get_or_create_application(db, user_id, job_id)
    app.status = status
    if notes is not None:
        app.notes = notes
    if status == "applied" and app.applied_at is None:
        app.applied_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(app)
    return app


def get_applications_for_user(db: Session, user_id: int) -> list[Application]:
    return (
        db.query(Application)
        .filter(Application.user_id == user_id)
        .order_by(Application.updated_at.desc())
        .all()
    )


def application_status_map(db: Session, user_id: int) -> dict[int, str]:
    apps = db.query(Application).filter(Application.user_id == user_id).all()
    return {a.job_id: a.status for a in apps}


# ---- Analytics ---------------------------------------------------------------


def get_stats(db: Session) -> dict:
    total = db.query(Job).count()
    by_source = {}
    for row in db.query(Job.source, func.count(Job.id)).group_by(Job.source).all():
        by_source[row[0]] = row[1]
    top_companies = [
        {"name": r[0], "count": r[1]}
        for r in db.query(Job.company, func.count(Job.id))
        .filter(Job.company.isnot(None))
        .group_by(Job.company)
        .order_by(func.count(Job.id).desc())
        .limit(10)
        .all()
    ]
    top_locations = [
        {"name": r[0], "count": r[1]}
        for r in db.query(Job.location, func.count(Job.id))
        .filter(Job.location.isnot(None))
        .group_by(Job.location)
        .order_by(func.count(Job.id).desc())
        .limit(10)
        .all()
    ]
    salaries = [j.salary for j in db.query(Job.salary).filter(Job.salary.isnot(None)).all() if j.salary]
    return {
        "total_jobs": total,
        "by_source": by_source,
        "top_companies": top_companies,
        "top_locations": top_locations,
        "salary_count": len(salaries),
    }


# ---- Salary parsing ----------------------------------------------------------


def parse_salary(s: str | None) -> dict | None:
    if not s:
        return None
    import re
    nums = [int(x.replace(",", "")) for x in re.findall(r"[\$€£]?([\d,]+)", s)]
    if not nums:
        return None
    hourly = "hour" in s.lower() or "/hr" in s.lower()
    factor = 2080 if hourly else 1  # hours per year
    annual = [n * factor for n in nums]
    return {
        "min": min(annual),
        "max": max(annual),
        "avg": sum(annual) // len(annual),
        "hourly": hourly,
        "raw": s,
    }


# ---- Resume matching ---------------------------------------------------------


def match_score(job: Job, resume_keywords: set[str]) -> int:
    if not resume_keywords:
        return 0
    text = " ".join(filter(None, [job.title, job.company, job.location, job.summary, job.description or ""])).lower()
    if not text:
        return 0
    matched = sum(1 for kw in resume_keywords if kw.lower() in text)
    return min(100, int(matched / max(len(resume_keywords), 1) * 100))
