from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.errors import INACTIVE_USER
from app.core.security import (
    check_login_password,
    create_access_token,
    hash_password_async,
)
from app.deps import AuditLog, DbSession
from app.models import LogLevel, User
from app.schemas.auth import Token
from app.schemas.user import UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register", response_model=UserRead, status_code=status.HTTP_201_CREATED
)
async def register(data: UserCreate, audit: AuditLog, db: DbSession) -> User:
    # New accounts are always active users; a `role` in the body is ignored
    user = User(
        username=data.username,
        email=data.email,
        hashed_password=await hash_password_async(data.password),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # Unique username/email. Deliberately not saying which one is taken.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered",
        ) from None
    await audit("register", f"{user.username} registered", user=user)
    return user


@router.post("/login", response_model=Token)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    audit: AuditLog,
    db: DbSession,
) -> Token:
    """OAuth2 password flow (form fields), so Swagger's Authorize works."""
    user = await db.scalar(select(User).where(User.username == form.username))
    hashed = user.hashed_password if user else None
    if not await check_login_password(form.password, hashed):
        await audit(
            "login_failed",
            f"Failed login for username {form.username}",
            user=user,
            level=LogLevel.WARNING,
        )
        # Same message whether the username or the password is wrong
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        await audit(
            "login_failed",
            f"Login refused for inactive user {user.username}",
            user=user,
            level=LogLevel.WARNING,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=INACTIVE_USER
        )
    await audit("login_success", f"{user.username} logged in", user=user)
    return Token(access_token=create_access_token(user.id, user.role))
