from sqlalchemy import func, select

from app.core.config import settings
from app.core.security import verify_password
from app.models import Role, User
from app.seed import seed_users


async def test_seed_creates_three_accounts_once(db):
    await seed_users(db)
    await seed_users(db)

    assert await db.scalar(select(func.count()).select_from(User)) == 3
    admin = await db.scalar(select(User).where(User.username == "admin"))
    assert admin.role == Role.admin
    assert verify_password(settings.seed_admin_password, admin.hashed_password)
