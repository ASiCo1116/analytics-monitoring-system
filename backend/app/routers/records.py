from typing import Annotated

from fastapi import APIRouter, Depends, Query, UploadFile, status

from app.deps import AuditLog, DbSession, WriterUser, get_current_user
from app.models import Record
from app.schemas.common import Page
from app.schemas.record import (
    BatchDeleteResult,
    ImportResult,
    RecordBatchDelete,
    RecordCreate,
    RecordListParams,
    RecordRead,
    RecordUpdate,
)
from app.services import import_service, record_service

# Every logged-in role may read. Writing needs WriterUser (Admin or User);
# changing or deleting an existing record also requires being its creator
# (or an Admin).
router = APIRouter(
    prefix="/records",
    tags=["records"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=Page[RecordRead])
async def list_records(
    params: Annotated[RecordListParams, Query()], db: DbSession
) -> Page[RecordRead]:
    records, total = await record_service.list_records(db, params)
    return Page[RecordRead].of(records, total, params)


@router.post("", response_model=RecordRead, status_code=status.HTTP_201_CREATED)
async def create_record(
    data: RecordCreate, audit: AuditLog, db: DbSession, user: WriterUser
) -> Record:
    record = await record_service.create_record(db, data, user)
    await audit(
        "record_create",
        f"{user.username} created record {record.id} ({record.title})",
        user=user,
    )
    return record


@router.post(
    "/import",
    response_model=ImportResult,
    status_code=status.HTTP_201_CREATED,
    responses={
        413: {"description": "More than 5 MB or 10,000 records"},
        415: {"description": "Not a CSV or JSON file"},
        422: {
            "description": "Row errors: {detail: {errors: [{row, field, "
            "message}]}}; nothing is imported"
        },
    },
)
async def import_records(
    file: UploadFile, audit: AuditLog, db: DbSession, user: WriterUser
) -> ImportResult:
    """Bulk create records from CSV or JSON; all rows or none are stored.

    CSV header: title,value,category,recorded_at,description (the last two
    may be empty). JSON: an array of objects with the same fields.
    """
    imported = await import_service.import_records(db, file, user)
    await audit(
        "record_import",
        f"{user.username} imported {imported} records from {file.filename}",
        user=user,
    )
    return ImportResult(imported=imported)


# Declared before /{record_id} so "categories" is not taken as an id
@router.get("/categories", response_model=list[str])
async def list_categories(db: DbSession) -> list[str]:
    """Distinct category names in alphabetical order."""
    return await record_service.list_categories(db)


@router.get("/{record_id}", response_model=RecordRead)
async def get_record(record_id: int, db: DbSession) -> Record:
    return await record_service.get_record(db, record_id)


@router.patch("/{record_id}", response_model=RecordRead)
async def update_record(
    record_id: int,
    data: RecordUpdate,
    audit: AuditLog,
    db: DbSession,
    user: WriterUser,
) -> Record:
    record, changed = await record_service.update_record(
        db, record_id, data, user
    )
    await audit(
        "record_update",
        f"{user.username} updated record {record.id} "
        f"({', '.join(changed) or 'no changes'})",
        user=user,
    )
    return record


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_record(
    record_id: int, audit: AuditLog, db: DbSession, user: WriterUser
) -> None:
    record = await record_service.delete_record(db, record_id, user)
    await audit(
        "record_delete",
        f"{user.username} deleted record {record_id} ({record.title})",
        user=user,
    )


@router.post(
    "/batch-delete",
    response_model=BatchDeleteResult,
    responses={
        403: {
            "description": "Viewer, or records created by someone else: "
            "{detail: {message, ids}}; nothing is deleted"
        },
        404: {
            "description": "Unknown ids: {detail: {message, ids}}; nothing "
            "is deleted"
        },
    },
)
async def batch_delete_records(
    data: RecordBatchDelete, audit: AuditLog, db: DbSession, user: WriterUser
) -> BatchDeleteResult:
    """Delete up to 100 records at once; all of them or none."""
    deleted = await record_service.delete_records(db, data.ids, user)
    await audit(
        "record_batch_delete",
        f"{user.username} deleted {deleted} records: "
        f"{', '.join(map(str, data.ids))}",
        user=user,
    )
    return BatchDeleteResult(deleted=deleted)
