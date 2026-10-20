from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.deps import DB, CurrentUser, utcnow
from app.core.ratelimit import SlidingWindowLimiter
from app.core.security import (
    hash_password,
    hash_token,
    needs_rehash,
    new_session_token,
    verify_password,
)
from app.models.org import User, UserSession
from app.schemas.org import LoginIn, PasswordChange, UserOut
from app.services.audit import audit

router = APIRouter(prefix="/auth", tags=["auth"])

_settings = get_settings()
login_limiter = SlidingWindowLimiter(_settings.login_max_attempts, _settings.login_window_seconds)


def _client_ip(request: Request) -> str:
    # Behind a reverse proxy, run uvicorn with --proxy-headers so this is the real client.
    return request.client.host if request.client else "unknown"


def _set_session_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        s.session_cookie_name,
        token,
        max_age=s.session_ttl_hours * 3600,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=UserOut)
async def login(body: LoginIn, request: Request, response: Response, db: DB) -> User:
    ip = _client_ip(request)
    keys = (f"ip:{ip}", f"user:{body.username.lower()}")
    if any(login_limiter.is_blocked(k) for k in keys):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts")

    user = await db.scalar(select(User).where(User.username == body.username))
    ok = await verify_password(body.password, user.password_hash if user else None)
    if not ok or user is None or not user.is_active:
        for k in keys:
            login_limiter.hit(k)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")

    login_limiter.reset(keys[1])
    now = utcnow()
    if needs_rehash(user.password_hash):
        user.password_hash = await hash_password(body.password)
    user.last_login_at = now

    token = new_session_token()
    db.add(
        UserSession(
            token_hash=hash_token(token),
            user_id=user.id,
            created_at=now,
            expires_at=now + timedelta(hours=get_settings().session_ttl_hours),
            ip_address=ip[:45],
            user_agent=(request.headers.get("user-agent") or "")[:255],
        )
    )
    # Opportunistic cleanup of this user's expired sessions.
    await db.execute(
        delete(UserSession).where(UserSession.user_id == user.id, UserSession.expires_at <= now)
    )
    audit(db, user, "login", "user", user.id, ip=ip)
    await db.commit()
    _set_session_cookie(response, token)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: DB) -> None:
    s = get_settings()
    token = request.cookies.get(s.session_cookie_name)
    if token:
        await db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))
        await db.commit()
    response.delete_cookie(s.session_cookie_name, path="/", secure=s.cookie_secure, httponly=True)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: PasswordChange, request: Request, user: CurrentUser, db: DB
) -> None:
    if not await verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.password_hash = await hash_password(body.new_password)
    # Sign out every other session for this user.
    await db.execute(
        delete(UserSession).where(
            UserSession.user_id == user.id, UserSession.id != request.state.session_id
        )
    )
    audit(db, user, "change_password", "user", user.id)
    await db.commit()
