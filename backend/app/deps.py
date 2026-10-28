"""Shared FastAPI dependencies: database session, current user, roles."""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import Role, User

# Fixed detail strings: the frontend uses "Inactive user" to tell a disabled
# account (log out) apart from a plain permission error (stay logged in).
INACTIVE_USER = "Inactive user"
NOT_ENOUGH_PERMISSIONS = "Not enough permissions"

DbSession = Annotated[AsyncSession, Depends(get_db)]

# tokenUrl powers the Authorize button in Swagger
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], db: DbSession
) -> User:
    """Resolve the token to a user, reading the user from the database.

    Reading on every request makes a disabled account or a role change take
    effect immediately; the role inside the token is never trusted.
    """
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        user_id = decode_access_token(token)
    except jwt.InvalidTokenError:
        raise credentials_error from None
    user = await db.get(User, user_id)
    if user is None:
        raise credentials_error
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=INACTIVE_USER
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role):
    """Dependency factory, e.g. Depends(require_roles(Role.admin))."""

    async def check_role(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=NOT_ENOUGH_PERMISSIONS,
            )
        return user

    return check_role


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
