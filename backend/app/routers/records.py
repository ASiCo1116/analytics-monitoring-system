from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, UploadFile, status

from app.deps import CurrentUser, DbSession, client_ip, require_roles
from app.models import Record, Role, User
from app.schemas.common import Page
from app.schemas.record import (
    ImportResult,
    RecordCreate,
    RecordListParams,
    RecordRead,
    RecordUpdate,
)
from app.services import audit_service, import_service, record_service

router = APIRouter(prefix="/records", tags=["records"])

# Writing records: Admin and User, never Viewer. Changing or deleting an
# existing record additionally requires being its creator (or an Admin).
Writer = Annotated[User, Depends(require_roles(Role.admin, Role.user))]


@router.get("", response_model=Page[RecordRead])
async def list_records(
    params: Annotated[RecordListParams, Query()],
    db: DbSession,
    _: CurrentUser,
) -> Page[RecordRead]:
    records, total = await record_service.list_records(db, params)
    return Page[RecordRead](
        items=[RecordRead.model_validate(r) for r in records],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("", response_model=RecordRead, status_code=status.HTTP_201_CREATED)
async def create_record(
    data: RecordCreate, request: Request, db: DbSession, user: Writer
) -> Record:
    record = await record_service.create_record(db, data, user)
    await audit_service.log(
        "record_create",
        f"{user.username} created record {record.id} ({record.title})",
        user_id=user.id,
        ip_address=client_ip(request),
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
    file: UploadFile, request: Request, db: DbSession, user: Writer
) -> ImportResult:
    """Bulk create records from CSV or JSON; all rows or none are stored.

    CSV header: title,value,category,recorded_at,description (the last two
    may be empty). JSON: an array of objects with the same fields.
    """
    imported = await import_service.import_records(db, file, user)
    await audit_service.log(
        "record_import",
        f"{user.username} imported {imported} records from {file.filename}",
        user_id=user.id,
        ip_address=client_ip(request),
    )
    return ImportResult(imported=imported)


# Declared before /{record_id} so "categories" is not taken as an id
@router.get("/categories", response_model=list[str])
async def list_categories(db: DbSession, _: CurrentUser) -> list[str]:
    """Distinct category names in alphabetical order."""
    return await record_service.list_categories(db)


@router.get("/{record_id}", response_model=RecordRead)
async def get_record(record_id: int, db: DbSession, _: CurrentUser) -> Record:
    return await record_service.get_record(db, record_id)


@router.patch("/{record_id}", response_model=RecordRead)
async def update_record(
    record_id: int,
    data: RecordUpdate,
    request: Request,
    db: DbSession,
    user: Writer,
) -> Record:
    record = await record_service.get_record(db, record_id)
    record_service.ensure_can_modify(record, user)
    record = await record_service.update_record(db, record, data)
    await audit_service.log(
        "record_update",
        f"{user.username} updated record {record.id} "
        f"({', '.join(sorted(data.model_fields_set)) or 'no fields'})",
        user_id=user.id,
        ip_address=client_ip(request),
    )
    return record


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_record(
    record_id: int, request: Request, db: DbSession, user: Writer
) -> None:
    record = await record_service.get_record(db, record_id)
    record_service.ensure_can_modify(record, user)
    await record_service.delete_record(db, record)
    await audit_service.log(
        "record_delete",
        f"{user.username} deleted record {record_id} ({record.title})",
        user_id=user.id,
        ip_address=client_ip(request),
    )
