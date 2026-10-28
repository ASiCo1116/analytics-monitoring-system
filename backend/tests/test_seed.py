from datetime import timedelta

from sqlalchemy import func, select

from app.core.config import settings
from app.core.security import verify_password
from app.db.base import utc_now
from app.models import Record, Role, User
from app.seed import SAMPLE_RECORD_COUNT, seed_records, seed_users


async def test_seed_creates_three_accounts_once(db):
    await seed_users(db)
    await seed_users(db)

    assert await db.scalar(select(func.count()).select_from(User)) == 3
    admin = await db.scalar(select(User).where(User.username == "admin"))
    assert admin.role == Role.admin
    assert verify_password(settings.seed_admin_password, admin.hashed_password)


async def test_seed_records_only_when_table_is_empty(db):
    await seed_users(db)

    await seed_records(db)
    await seed_records(db)

    total = await db.scalar(select(func.count()).select_from(Record))
    assert total == SAMPLE_RECORD_COUNT
    oldest = await db.scalar(select(func.min(Record.recorded_at)))
    assert oldest >= utc_now() - timedelta(days=30, minutes=1)
    owners = await db.scalars(
        select(User.username)
        .join(Record, Record.owner_id == User.id)
        .distinct()
    )
    assert set(owners) == {"admin", "user"}
