from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Favorite, Job, SavedSearch, User
from app.services.jobs import add_favorite, remove_favorite
from app.templating import templates

router = APIRouter(tags=["account"])


def _ctx(current_user: User, **kw) -> dict:
    return {"current_user": current_user, **kw}


# ---- Favorites ---------------------------------------------------------------


@router.post("/favorites/{job_id}")
def toggle_favorite(
    request: Request,
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not db.get(Job, job_id):
        raise HTTPException(status_code=404, detail="Job not found")

    from app.services.jobs import is_favorite

    if is_favorite(db, current_user.id, job_id):
        remove_favorite(db, current_user.id, job_id)
    else:
        add_favorite(db, current_user.id, job_id)

    back = request.headers.get("referer") or f"/jobs/{job_id}"
    return RedirectResponse(url=back, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/favorites")
def favorites_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    jobs = (
        db.execute(
            select(Job)
            .join(Favorite, Favorite.job_id == Job.id)
            .where(Favorite.user_id == current_user.id)
            .order_by(Job.first_seen_at.desc())
        )
        .scalars()
        .all()
    )
    items = [{"job": j, "is_favorite": True} for j in jobs]
    return templates.TemplateResponse(
        request, "favorites.html", _ctx(current_user, items=items, per_page=10)
    )


@router.delete("/favorites/{job_id}")
def delete_favorite(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    remove_favorite(db, current_user.id, job_id)
    return RedirectResponse(url="/favorites", status_code=status.HTTP_303_SEE_OTHER)


# ---- Saved searches ----------------------------------------------------------


@router.post("/saved-searches")
def save_search(
    request: Request,
    q: str = Form(...),
    l: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exists = (
        db.query(SavedSearch)
        .filter(
            SavedSearch.user_id == current_user.id,
            SavedSearch.keyword == q.strip(),
            SavedSearch.location == l.strip(),
        )
        .first()
    )
    if not exists:
        db.add(SavedSearch(user_id=current_user.id, keyword=q.strip(), location=l.strip()))
        db.commit()
    back = request.headers.get("referer") or "/"
    return RedirectResponse(url=back, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/saved-searches")
def saved_searches(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    searches = (
        db.query(SavedSearch)
        .filter(SavedSearch.user_id == current_user.id)
        .order_by(SavedSearch.id.desc())
        .all()
    )
    return templates.TemplateResponse(
        request, "saved_searches.html", _ctx(current_user, searches=searches)
    )


@router.post("/saved-searches/{search_id}/delete")
def delete_saved_search(
    search_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = db.get(SavedSearch, search_id)
    if row and row.user_id == current_user.id:
        db.delete(row)
        db.commit()
    return RedirectResponse(url="/saved-searches", status_code=status.HTTP_303_SEE_OTHER)
