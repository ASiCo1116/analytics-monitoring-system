import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.deps import AdminUser, AuditLog, DbSession, require_admin
from app.models import User
from app.schemas.admin import (
    DbStatus,
    LogListParams,
    SystemLogRead,
    UserAdminUpdate,
    UserListParams,
)
from app.schemas.common import Page
from app.schemas.user import UserRead
from app.services import admin_service

router = APIRouter(
    prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)]
)


@router.get("/users", response_model=Page[UserRead])
async def list_users(
    params: Annotated[UserListParams, Query()], db: DbSession
) -> Page[UserRead]:
    users, total = await admin_service.list_users(db, params)
    return Page[UserRead].of(users, total, params)


@router.patch(
    "/users/{user_id}",
    response_model=UserRead,
    responses={400: {"description": "Changing your own role or status"}},
)
async def update_user(
    user_id: uuid.UUID,
    data: UserAdminUpdate,
    audit: AuditLog,
    db: DbSession,
    admin: AdminUser,
) -> User:
    """Change a user's role and/or active status (not your own)."""
    user, changes = await admin_service.update_user(db, admin, user_id, data)
    if "role" in changes:
        old, new = changes["role"]
        await audit(
            "role_change",
            f"{admin.username} changed the role of {user.username} "
            f"from {old} to {new}",
            user=admin,
        )
    if "is_active" in changes:
        verb = "activated" if user.is_active else "deactivated"
        await audit(
            "user_status_change",
            f"{admin.username} {verb} {user.username}",
            user=admin,
        )
    return user


@router.get("/logs", response_model=Page[SystemLogRead])
async def list_logs(
    params: Annotated[LogListParams, Query()], db: DbSession
) -> Page[SystemLogRead]:
    """Audit events, newest first."""
    logs, total = await admin_service.list_logs(db, params)
    return Page[SystemLogRead].of(logs, total, params)


@router.get("/db-status", response_model=DbStatus)
async def db_status(db: DbSession) -> DbStatus:
    """Database connection, pool, table sizes and the metric buffer.

    503 when the database cannot be reached.
    """
    return await admin_service.db_status(db)
