from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_optional_user
from app.models import User
from app.ratelimit import limiter
from app.schemas import JobOut
from app.services.jobs import favorite_ids_for_user, get_job, upsert_jobs
from app.scraper import router as source_router
from app.scraper.router import NoSourceAvailable
from app.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])
PER_PAGE = 10


def _ctx(current_user: User | None = None, **kw) -> dict:
    return {"current_user": current_user, **kw}


@router.get("/search")
@limiter.limit("30/minute")
def search(
    request: Request,
    q: str = Query(default=""),
    l: str = Query(default=""),
    page: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    q, l = q.strip(), l.strip()
    error = None
    jobs = []
    source_used = None
    total = 0

    if q or l:
        try:
            result = source_router.fetch_jobs(db, q, l, page)
            jobs = upsert_jobs(db, result.jobs)
            source_used = result.source
            total = result.total
        except NoSourceAvailable as exc:
            error = str(exc)
            logger.warning("search failed: %s", exc)

    fav_ids = favorite_ids_for_user(db, current_user.id) if current_user else set()
    items = [{"job": j, "is_favorite": j.id in fav_ids} for j in jobs]

    ctx = _ctx(
        current_user,
        q=q, l=l, page=page, source=source_used, total=total,
        items=items, error=error, per_page=PER_PAGE,
    )

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "_job_list.html", ctx)
    return templates.TemplateResponse(request, "search_results.html", ctx)


@router.get("/jobs/{job_id}")
def job_detail(
    request: Request,
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    job = get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    is_fav = False
    if current_user:
        from app.services.jobs import is_favorite

        is_fav = is_favorite(db, current_user.id, job.id)
    return templates.TemplateResponse(
        request,
        "job_detail.html",
        _ctx(current_user, job=job, is_favorite=is_fav),
    )


@router.get("/api/jobs", response_model=list[JobOut])
@limiter.limit("30/minute")
def api_search(
    request: Request,
    q: str = Query(default=""),
    l: str = Query(default=""),
    page: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    if not (q or l):
        return []
    try:
        result = source_router.fetch_jobs(db, q.strip(), l.strip(), page)
    except NoSourceAvailable:
        return []
    jobs = upsert_jobs(db, result.jobs)
    return [JobOut.model_validate(j) for j in jobs]
