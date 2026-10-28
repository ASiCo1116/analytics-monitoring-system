"""User management, audit log queries and database status for Admins."""

import time
import uuid

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.session import engine
from app.models import Metric, Record, SystemLog, User
from app.realtime.buffer import metric_buffer
from app.schemas.admin import (
    BufferStatus,
    DbStatus,
    LogListParams,
    PoolStatus,
    UserAdminUpdate,
    UserListParams,
)
from app.services.paging import page_of

COUNTED_TABLES = (User, Record, Metric, SystemLog)


def _filtered_users(query: Select, params: UserListParams) -> Select:
    if params.role is not None:
        query = query.where(User.role == params.role)
    if params.is_active is not None:
        query = query.where(User.is_active == params.is_active)
    if params.q:
        query = query.where(User.username.contains(params.q, autoescape=True))
    return query


async def list_users(
    db: AsyncSession, params: UserListParams
) -> tuple[list[User], int]:
    total = await db.scalar(
        _filtered_users(select(func.count()).select_from(User), params)
    )
    # UUIDv7 ids follow creation order
    query = _filtered_users(select(User), params).order_by(User.id)
    users = await db.scalars(page_of(query, params))
    return list(users), total


async def update_user(
    db: AsyncSession, admin: User, user_id: uuid.UUID, data: UserAdminUpdate
) -> tuple[User, dict[str, tuple[object, object]]]:
    """Apply the changes; returns the user and {field: (old, new)}.

    Only fields whose value really changes are listed.
    """
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    changes = {
        name: (getattr(user, name), value)
        for name, value in data.model_dump(exclude_unset=True).items()
        if getattr(user, name) != value
    }
    # An Admin who demotes or disables themselves could leave the system
    # without any Admin
    if user.id == admin.id and changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot change your own role or active status",
        )
    for name, (_, new) in changes.items():
        setattr(user, name, new)
    await db.commit()
    return user, changes


def _filtered_logs(query: Select, params: LogListParams) -> Select:
    if params.level is not None:
        query = query.where(SystemLog.level == params.level)
    if params.action is not None:
        query = query.where(SystemLog.action == params.action)
    if params.user_id is not None:
        query = query.where(SystemLog.user_id == params.user_id)
    if params.start is not None:
        query = query.where(SystemLog.created_at >= params.start)
    if params.end is not None:
        query = query.where(SystemLog.created_at < params.end)
    return query


async def list_logs(
    db: AsyncSession, params: LogListParams
) -> tuple[list[SystemLog], int]:
    total = await db.scalar(
        _filtered_logs(select(func.count()).select_from(SystemLog), params)
    )
    query = (
        _filtered_logs(select(SystemLog), params)
        .options(joinedload(SystemLog.user))
        .order_by(SystemLog.created_at.desc(), SystemLog.id.desc())
    )
    logs = await db.scalars(page_of(query, params))
    return list(logs), total


async def db_status(db: AsyncSession) -> DbStatus:
    """Connection, pool, table sizes and the metric buffer.

    A database that cannot be reached raises OperationalError, which the
    app turns into 503; so a response always means connected=true.
    """
    started = time.perf_counter()
    await db.execute(select(func.now()))
    response_ms = (time.perf_counter() - started) * 1000

    # Exact counts; COUNT(*) on metrics grows slower as data piles up
    # (about 780,000 rows a day, see design Risks)
    tables = {
        model.__tablename__: await db.scalar(
            select(func.count()).select_from(model)
        )
        for model in COUNTED_TABLES
    }

    pool = engine.pool
    last = metric_buffer.last_flush
    return DbStatus(
        connected=True,
        response_ms=round(response_ms, 2),
        pool=PoolStatus(
            size=pool.size(),
            checked_out=pool.checkedout(),
            idle=pool.checkedin(),
            # Starts negative (connections not opened yet); 0 means none
            # beyond the pool size
            overflow=max(pool.overflow(), 0),
        ),
        tables=tables,
        buffer=BufferStatus(
            pending=len(metric_buffer),
            last_flush_at=last.at if last else None,
            last_flush_count=last.count if last else None,
            last_flush_reason=last.reason if last else None,
        ),
    )
