"""Create the test accounts. Safe to run repeatedly: `python -m app.seed`."""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models import Role, User

logger = logging.getLogger(__name__)


def seed_accounts() -> list[tuple[str, Role, str]]:
    """(username, role, password); passwords come from the environment."""
    return [
        ("admin", Role.admin, settings.seed_admin_password),
        ("user", Role.user, settings.seed_user_password),
        ("viewer", Role.viewer, settings.seed_viewer_password),
    ]


async def seed_users(session: AsyncSession) -> None:
    """Create each test account that does not exist yet."""
    for username, role, password in seed_accounts():
        exists = await session.scalar(
            select(User.id).where(User.username == username)
        )
        if exists:
            continue
        session.add(
            User(
                username=username,
                email=f"{username}@example.com",
                hashed_password=hash_password(password),
                role=role,
            )
        )
        logger.info("Created test account %s (%s)", username, role)
    await session.commit()


async def main() -> None:
    setup_logging(settings.log_level)
    async with SessionLocal() as session:
        await seed_users(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
