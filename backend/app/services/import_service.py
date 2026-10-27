"""Bulk import of data records from CSV or JSON files (all or nothing)."""

import csv
import io
import json
from pathlib import PurePath
from typing import Any

from fastapi import HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.schemas.record import RecordCreate
from app.services.record_service import new_record

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 10_000
COLUMNS = ("title", "value", "category", "recorded_at", "description")
REQUIRED_COLUMNS = {"title", "value", "category"}


def _unprocessable(errors: list[dict[str, Any]]) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"errors": errors},
    )


def _file_error(message: str) -> HTTPException:
    # Problems with the file as a whole are reported as row 0
    return _unprocessable([{"row": 0, "field": None, "message": message}])


def _detect_format(upload: UploadFile) -> str:
    suffix = PurePath(upload.filename or "").suffix.lower()
    content_type = (upload.content_type or "").split(";")[0].strip()
    if suffix == ".csv" or content_type == "text/csv":
        return "csv"
    if suffix == ".json" or content_type == "application/json":
        return "json"
    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Only CSV and JSON files are supported",
    )


def _parse_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
    if missing:
        raise _file_error(
            f"Missing CSV header columns: {', '.join(sorted(missing))}"
        )
    # Empty cells mean "not given", so optional fields fall back to defaults
    return [{name: row.get(name) or None for name in COLUMNS} for row in reader]


def _parse_json(text: str) -> list[Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _file_error(f"Invalid JSON: {exc.msg}") from None
    if not isinstance(data, list):
        raise _file_error("JSON must be an array of objects")
    return data


def _validate(rows: list[Any]) -> list[RecordCreate]:
    """Validate every row; raise one 422 listing all errors, if any."""
    valid: list[RecordCreate] = []
    errors: list[dict[str, Any]] = []
    # Rows are numbered from 1, like the data rows seen in a spreadsheet
    for number, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(
                {"row": number, "field": None, "message": "Not an object"}
            )
            continue
        try:
            valid.append(RecordCreate.model_validate(row))
        except ValidationError as exc:
            errors.extend(
                {
                    "row": number,
                    "field": str(error["loc"][0]) if error["loc"] else None,
                    "message": error["msg"],
                }
                for error in exc.errors()
            )
    if errors:
        raise _unprocessable(errors)
    return valid


async def import_records(
    db: AsyncSession, upload: UploadFile, owner: User
) -> int:
    file_format = _detect_format(upload)
    content = await upload.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File is larger than {MAX_FILE_BYTES // 1024 // 1024} MB",
        )
    try:
        # utf-8-sig also accepts the BOM that Excel adds to CSV files
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise _file_error("File must be UTF-8 encoded") from None

    rows = _parse_csv(text) if file_format == "csv" else _parse_json(text)
    if len(rows) > MAX_ROWS:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File has more than {MAX_ROWS} records",
        )
    if not rows:
        raise _file_error("File contains no records")

    records = [new_record(data, owner) for data in _validate(rows)]
    # One transaction: either every row is stored or none
    db.add_all(records)
    await db.commit()
    return len(records)
