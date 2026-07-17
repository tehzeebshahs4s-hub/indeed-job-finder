from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_optional_user
from app.models import User
from app.security import COOKIE_NAME, create_access_token, get_user_by_email, hash_password, verify_password
from app.templating import templates

router = APIRouter(tags=["pages"])


def _ctx(current_user: User | None = None, **kw) -> dict:
    return {"current_user": current_user, **kw}


@router.get("/")
def index(request: Request, current_user: User | None = Depends(get_optional_user)):
    return templates.TemplateResponse(request, "index.html", _ctx(current_user))


@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", _ctx())


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_user_by_email(db, username)
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            request, "login.html", {**_ctx(), "error": "Invalid email or password"}, status_code=401
        )
    resp = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    resp.set_cookie(
        key=COOKIE_NAME,
        value=create_access_token(user.email),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
        path="/",
    )
    return resp


@router.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", _ctx())


@router.post("/register")
def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if len(password) < 8:
        return templates.TemplateResponse(
            request, "register.html", {**_ctx(), "error": "Password must be at least 8 characters"}
        )
    if get_user_by_email(db, email):
        return templates.TemplateResponse(
            request, "register.html", {**_ctx(), "error": "Email already registered"}
        )
    db.add(User(email=email, hashed_password=hash_password(password)))
    db.commit()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
