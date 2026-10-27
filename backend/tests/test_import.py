import json

from sqlalchemy import func, select

from app.models import Record, Role, SystemLog
from app.services.import_service import MAX_ROWS

IMPORT = "/api/v1/records/import"
HEADER = "title,value,category,recorded_at,description\n"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def csv_file(rows: list[str], name: str = "records.csv"):
    content = HEADER + "".join(row + "\n" for row in rows)
    return {"file": (name, content.encode(), "text/csv")}


def valid_rows(count: int) -> list[str]:
    return [
        f"Sales {i},{i}.5,sales,2026-10-01 08:00:00,row {i}"
        for i in range(1, count + 1)
    ]


async def record_count(db) -> int:
    return await db.scalar(select(func.count()).select_from(Record))


async def test_csv_import(client, db, users, auth_headers):
    response = await client.post(
        IMPORT, files=csv_file(valid_rows(50)), headers=auth_headers[Role.user]
    )

    assert response.status_code == 201
    assert response.json() == {"imported": 50}
    owners = (await db.scalars(select(Record.owner_id).distinct())).all()
    assert owners == [users[Role.user].id]
    log = await db.scalar(
        select(SystemLog).where(SystemLog.action == "record_import")
    )
    assert "50 records" in log.message


async def test_csv_optional_columns_may_be_empty(client, db, auth_headers):
    response = await client.post(
        IMPORT,
        files=csv_file(["Only required,1,sales,,"]),
        headers=auth_headers[Role.user],
    )

    assert response.status_code == 201
    record = await db.scalar(select(Record))
    assert record.description is None
    assert record.recorded_at is not None  # defaults to now


async def test_rows_with_errors_import_nothing(client, db, auth_headers):
    rows = valid_rows(8)
    rows[2] = "Bad 3,abc,sales,,"  # data row 3
    rows[6] = "Bad 7,xyz,sales,,"  # data row 7

    response = await client.post(
        IMPORT, files=csv_file(rows), headers=auth_headers[Role.user]
    )

    assert response.status_code == 422
    errors = response.json()["detail"]["errors"]
    assert [(e["row"], e["field"]) for e in errors] == [
        (3, "value"),
        (7, "value"),
    ]
    assert await record_count(db) == 0


async def test_json_import(client, auth_headers):
    items = [
        {"title": "A", "value": 1, "category": "traffic"},
        {"title": "B", "value": 2, "category": "traffic", "description": "x"},
    ]

    response = await client.post(
        IMPORT,
        files={"file": ("data.json", json.dumps(items), "application/json")},
        headers=auth_headers[Role.user],
    )

    assert response.status_code == 201
    assert response.json() == {"imported": 2}


async def test_json_must_be_array(client, auth_headers):
    response = await client.post(
        IMPORT,
        files={"file": ("data.json", '{"title": "A"}', "application/json")},
        headers=auth_headers[Role.user],
    )

    assert response.status_code == 422


async def test_missing_csv_header_column(client, auth_headers):
    response = await client.post(
        IMPORT,
        files={"file": ("x.csv", b"title,category\nA,sales\n", "text/csv")},
        headers=auth_headers[Role.user],
    )

    assert response.status_code == 422
    assert "value" in response.json()["detail"]["errors"][0]["message"]


async def test_unsupported_format(client, auth_headers):
    response = await client.post(
        IMPORT,
        files={
            "file": (
                "data.xlsx",
                b"PK\x03\x04",
                XLSX_TYPE,
            )
        },
        headers=auth_headers[Role.user],
    )

    assert response.status_code == 415


async def test_too_many_rows(client, db, auth_headers):
    response = await client.post(
        IMPORT,
        files=csv_file(valid_rows(MAX_ROWS + 1)),
        headers=auth_headers[Role.user],
    )

    assert response.status_code == 413
    assert await record_count(db) == 0


async def test_file_too_large(client, auth_headers):
    big = HEADER + "x" * (5 * 1024 * 1024)

    response = await client.post(
        IMPORT,
        files={"file": ("big.csv", big.encode(), "text/csv")},
        headers=auth_headers[Role.user],
    )

    assert response.status_code == 413


async def test_viewer_cannot_import(client, auth_headers):
    response = await client.post(
        IMPORT, files=csv_file(valid_rows(1)), headers=auth_headers[Role.viewer]
    )

    assert response.status_code == 403
