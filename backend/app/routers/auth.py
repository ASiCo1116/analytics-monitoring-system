from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.security import (
    check_login_password,
    create_access_token,
    hash_password_async,
)
from app.deps import INACTIVE_USER, DbSession, client_ip
from app.models import LogLevel, User
from app.schemas.auth import Token
from app.schemas.user import UserCreate, UserRead
from app.services import audit_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register", response_model=UserRead, status_code=status.HTTP_201_CREATED
)
async def register(data: UserCreate, request: Request, db: DbSession) -> User:
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
    await audit_service.log(
        "register",
        f"{user.username} registered",
        user_id=user.id,
        ip_address=client_ip(request),
    )
    return user


@router.post("/login", response_model=Token)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    request: Request,
    db: DbSession,
) -> Token:
    """OAuth2 password flow (form fields), so Swagger's Authorize works."""
    ip = client_ip(request)
    user = await db.scalar(select(User).where(User.username == form.username))
    hashed = user.hashed_password if user else None
    if not await check_login_password(form.password, hashed):
        await audit_service.log(
            "login_failed",
            f"Failed login for username {form.username}",
            level=LogLevel.WARNING,
            user_id=user.id if user else None,
            ip_address=ip,
        )
        # Same message whether the username or the password is wrong
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        await audit_service.log(
            "login_failed",
            f"Login refused for inactive user {user.username}",
            level=LogLevel.WARNING,
            user_id=user.id,
            ip_address=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=INACTIVE_USER
        )
    await audit_service.log(
        "login_success",
        f"{user.username} logged in",
        user_id=user.id,
        ip_address=ip,
    )
    return Token(access_token=create_access_token(user.id, user.role))
