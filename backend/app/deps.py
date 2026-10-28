"""Shared FastAPI dependencies: database session, current user, roles."""

from collections.abc import Awaitable, Callable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    INACTIVE_USER,
    INVALID_CREDENTIALS,
    NOT_ENOUGH_PERMISSIONS,
)
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import LogLevel, Role, User
from app.services import audit_service

DbSession = Annotated[AsyncSession, Depends(get_db)]

# tokenUrl powers the Authorize button in Swagger
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def user_for_token(db: AsyncSession, token: str) -> User | None:
    """The user a valid token belongs to (active or not), or None.

    Shared by the HTTP dependency and the WebSocket endpoint; each maps
    None and inactive users to its own response.
    """
    try:
        user_id = decode_access_token(token)
    except jwt.InvalidTokenError:
        return None
    return await db.get(User, user_id)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], db: DbSession
) -> User:
    """Resolve the token to a user, reading the user from the database.

    Reading on every request makes a disabled account or a role change take
    effect immediately; the role inside the token is never trusted.
    """
    user = await user_for_token(db, token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=INACTIVE_USER
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role) -> Callable[..., Awaitable[User]]:
    """Dependency factory, e.g. Depends(require_roles(Role.admin))."""

    async def check_role(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=NOT_ENOUGH_PERMISSIONS,
            )
        return user

    return check_role


# One dependency object per rule, so FastAPI runs it once per request even
# when both a router and one of its endpoints ask for it
require_admin = require_roles(Role.admin)
# Writing records: Admin and User, never Viewer
require_writer = require_roles(Role.admin, Role.user)

AdminUser = Annotated[User, Depends(require_admin)]
WriterUser = Annotated[User, Depends(require_writer)]


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


class Audit:
    """Writes audit events tagged with this request's client IP."""

    def __init__(self, request: Request) -> None:
        self.ip_address = client_ip(request)

    async def __call__(
        self,
        action: str,
        message: str,
        *,
        user: User | None = None,
        level: LogLevel = LogLevel.INFO,
    ) -> None:
        await audit_service.log(
            action,
            message,
            level=level,
            user_id=user.id if user else None,
            ip_address=self.ip_address,
        )


AuditLog = Annotated[Audit, Depends()]
