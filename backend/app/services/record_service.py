"""Business logic and queries for data records."""

from fastapi import HTTPException, status
from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.errors import NOT_ENOUGH_PERMISSIONS
from app.db.base import utc_now
from app.models import Record, Role, User
from app.schemas.record import RecordCreate, RecordListParams, RecordUpdate
from app.services.paging import page_of

SORT_COLUMNS = {
    "recorded_at": Record.recorded_at,
    "value": Record.value,
    "title": Record.title,
    "category": Record.category,
    "created_at": Record.created_at,
}


def new_record(data: RecordCreate, owner: User) -> Record:
    record = Record(
        **data.model_dump(exclude={"recorded_at"}),
        recorded_at=data.recorded_at or utc_now(),
        owner_id=owner.id,
    )
    # Set the relationship too, so the response can show the owner's name
    # without another query
    record.owner = owner
    return record


async def create_record(
    db: AsyncSession, data: RecordCreate, owner: User
) -> Record:
    record = new_record(data, owner)
    db.add(record)
    await db.commit()
    return record


def _filtered(query: Select, params: RecordListParams) -> Select:
    if params.category is not None:
        query = query.where(Record.category == params.category)
    if params.min_value is not None:
        query = query.where(Record.value >= params.min_value)
    if params.max_value is not None:
        query = query.where(Record.value <= params.max_value)
    if params.start is not None:
        query = query.where(Record.recorded_at >= params.start)
    if params.end is not None:
        query = query.where(Record.recorded_at < params.end)
    if params.q:
        query = query.where(Record.title.contains(params.q, autoescape=True))
    return query


async def list_records(
    db: AsyncSession, params: RecordListParams
) -> tuple[list[Record], int]:
    total = await db.scalar(
        _filtered(select(func.count()).select_from(Record), params)
    )

    column = SORT_COLUMNS[params.sort.removeprefix("-")]
    order = column.desc() if params.sort.startswith("-") else column.asc()
    query = (
        _filtered(select(Record), params)
        .options(joinedload(Record.owner))
        # id as tie-breaker keeps pages stable when sort values are equal
        .order_by(order, Record.id.desc())
    )
    records = await db.scalars(page_of(query, params))
    return list(records), total


async def get_record(db: AsyncSession, record_id: int) -> Record:
    record = await db.get(Record, record_id, options=[joinedload(Record.owner)])
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Record not found"
        )
    return record


def can_modify(record: Record, user: User) -> bool:
    """Only the creator or an Admin may change or delete a record."""
    return user.role == Role.admin or record.owner_id == user.id


def _ensure_can_modify(record: Record, user: User) -> None:
    if not can_modify(record, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=NOT_ENOUGH_PERMISSIONS,
        )


async def update_record(
    db: AsyncSession, record_id: int, data: RecordUpdate, user: User
) -> tuple[Record, list[str]]:
    """Partial update by the creator or an Admin (404, then 403).

    Only the fields sent are considered and the owner never changes.
    Returns the record and the names of the fields whose value changed.
    """
    record = await get_record(db, record_id)
    _ensure_can_modify(record, user)
    sent = data.model_dump(exclude_unset=True)
    changed = [
        name for name, value in sent.items() if getattr(record, name) != value
    ]
    for name in changed:
        setattr(record, name, sent[name])
    await db.commit()
    return record, changed


async def delete_record(db: AsyncSession, record_id: int, user: User) -> Record:
    """Delete as the creator or an Admin (404, then 403).

    Returns the deleted record, still readable for the audit message.
    """
    record = await get_record(db, record_id)
    _ensure_can_modify(record, user)
    await db.delete(record)
    await db.commit()
    return record


async def delete_records(db: AsyncSession, ids: list[int], user: User) -> int:
    """Delete every record in `ids`, or none of them.

    404 when an id does not exist, then 403 when the user may not delete
    one of them; both list the offending ids. Returns the number deleted.
    """
    records = (await db.scalars(select(Record).where(Record.id.in_(ids)))).all()
    missing = sorted(set(ids) - {record.id for record in records})
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Records not found", "ids": missing},
        )
    forbidden = sorted(r.id for r in records if not can_modify(r, user))
    if forbidden:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"message": NOT_ENOUGH_PERMISSIONS, "ids": forbidden},
        )
    result = await db.execute(delete(Record).where(Record.id.in_(ids)))
    await db.commit()
    return result.rowcount


async def list_categories(db: AsyncSession) -> list[str]:
    query = select(Record.category).distinct().order_by(Record.category)
    return list(await db.scalars(query))
