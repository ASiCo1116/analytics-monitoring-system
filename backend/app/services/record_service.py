"""Business logic and queries for data records."""

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.base import utc_now
from app.deps import NOT_ENOUGH_PERMISSIONS
from app.models import Record, Role, User
from app.schemas.record import RecordCreate, RecordListParams, RecordUpdate

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
        .offset((params.page - 1) * params.page_size)
        .limit(params.page_size)
    )
    records = (await db.scalars(query)).all()
    return list(records), total


async def get_record(db: AsyncSession, record_id: int) -> Record:
    record = await db.get(Record, record_id, options=[joinedload(Record.owner)])
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Record not found"
        )
    return record


def ensure_can_modify(record: Record, user: User) -> None:
    """Only the creator or an Admin may change or delete a record."""
    if user.role != Role.admin and record.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=NOT_ENOUGH_PERMISSIONS,
        )


async def update_record(
    db: AsyncSession, record: Record, data: RecordUpdate
) -> Record:
    # Only the fields present in the request; the owner is never changed
    for name, value in data.model_dump(exclude_unset=True).items():
        setattr(record, name, value)
    await db.commit()
    return record


async def delete_record(db: AsyncSession, record: Record) -> None:
    await db.delete(record)
    await db.commit()


async def list_categories(db: AsyncSession) -> list[str]:
    query = select(Record.category).distinct().order_by(Record.category)
    return list((await db.scalars(query)).all())
