from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_optional_user
from app.models import Application, Job, User
from app.services.jobs import (
    APP_STATUSES,
    get_applications_for_user,
    get_stats,
    match_score,
    parse_salary,
    search_jobs_db,
    update_application_status,
)
from app.templating import templates

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    stats = get_stats(db)
    # salary insights
    all_jobs = db.query(Job).filter(Job.salary.isnot(None)).all()
    salaries = [parse_salary(j.salary) for j in all_jobs]
    salaries = [s for s in salaries if s]
    salary_insight = None
    if salaries:
        salary_insight = {
            "min": min(s["min"] for s in salaries),
            "max": max(s["max"] for s in salaries),
            "avg": sum(s["avg"] for s in salaries) // len(salaries),
            "count": len(salaries),
        }
    # new jobs (last 24h)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    new_count = db.query(Job).filter(Job.first_seen_at > cutoff).count()

    # application summary for logged-in user
    app_summary = None
    if current_user:
        apps = get_applications_for_user(db, current_user.id)
        app_summary = {s: sum(1 for a in apps if a.status == s) for s in APP_STATUSES}
        app_summary["total"] = len(apps)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "current_user": current_user,
            "stats": stats,
            "salary_insight": salary_insight,
            "new_count": new_count,
            "app_summary": app_summary,
        },
    )


@router.get("/applications")
def applications(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    apps = get_applications_for_user(db, current_user.id)
    items = []
    for a in apps:
        job = db.get(Job, a.job_id)
        if job:
            items.append({"job": job, "status": a.status, "notes": a.notes, "updated": a.updated_at})
    return templates.TemplateResponse(
        request,
        "applications.html",
        {"current_user": current_user, "items": items, "statuses": APP_STATUSES},
    )


@router.post("/applications/{job_id}")
def update_application(
    request: Request,
    job_id: int,
    status: str = Form(...),
    notes: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if status not in APP_STATUSES:
        status = "bookmarked"
    update_application_status(db, current_user.id, job_id, status, notes or None)
    from fastapi.responses import RedirectResponse
    back = request.headers.get("referer") or f"/jobs/{job_id}"
    return RedirectResponse(url=back, status_code=303)


@router.get("/match")
def match_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    return templates.TemplateResponse(
        request, "match.html", {"current_user": current_user, "results": None, "resume": ""}
    )


@router.post("/match")
def match_submit(
    request: Request,
    resume: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    import re
    keywords = set(re.findall(r"[a-zA-Z+#]{3,}", resume.lower()))
    # Filter to meaningful keywords
    stop = {"the", "and", "for", "with", "you", "are", "was", "this", "that", "have", "from", "they", "will", "your", "all", "but", "not", "can", "had", "her", "has", "his", "him", "she", "its", "our", "out", "who", "what", "when", "why", "how", "any", "too", "very"}
    keywords = {k for k in keywords if k not in stop and len(k) >= 3}

    jobs, _ = search_jobs_db(db, "", "", 0, 50)
    results = []
    for job in jobs:
        score = match_score(job, keywords)
        if score > 0:
            results.append({"job": job, "score": score, "matched_keywords": [k for k in keywords if k in (job.title + " " + (job.summary or "")).lower()][:8]})
    results.sort(key=lambda x: x["score"], reverse=True)

    return templates.TemplateResponse(
        request,
        "match.html",
        {"current_user": current_user, "results": results[:20], "resume": resume, "kw_count": len(keywords)},
    )


@router.get("/export/csv")
def export_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.jobs import is_favorite

    fav_job_ids = [r[0] for r in db.query(Application.job_id).filter(Application.user_id == current_user.id).all()]
    jobs = db.query(Job).filter(Job.id.in_(fav_job_ids)).all() if fav_job_ids else []
    apps = {a.job_id: a.status for a in get_applications_for_user(db, current_user.id)}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Title", "Company", "Location", "Salary", "Source", "Status", "URL", "Posted"])
    for job in jobs:
        writer.writerow([
            job.title,
            job.company or "",
            job.location or "",
            job.salary or "",
            job.source,
            apps.get(job.id, ""),
            job.url or "",
            job.posted_at or "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=my_jobs.csv"},
    )


@router.get("/feed")
def rss_feed(db: Session = Depends(get_db)):
    jobs = db.query(Job).order_by(Job.first_seen_at.desc()).limit(50).all()
    items = []
    for job in jobs:
        items.append(f"""    <item>
      <title>{_escape(job.title)}</title>
      <link>{_escape(job.url or "")}</link>
      <description>{_escape(job.summary or "")}</description>
      <category>{_escape(job.company or "")}</category>
      <pubDate>{job.first_seen_at.strftime("%a, %d %b %Y %H:%M:%S +0000") if job.first_seen_at else ""}</pubDate>
    </item>""")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Indeed Job Finder - Latest Jobs</title>
    <link>https://tehzeebshahs4s-hub.github.io/indeed-job-finder/</link>
    <description>Latest Indeed jobs scraped daily</description>
    <language>en</language>
{chr(10).join(items)}
  </channel>
</rss>"""
    from fastapi.responses import Response
    return Response(content=xml, media_type="application/rss+xml")


def _escape(s: str | None) -> str:
    if not s:
        return ""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")