"""Create the test accounts and sample records.

Safe to run repeatedly: `python -m app.seed`.
"""

import asyncio
import logging
import random
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.security import hash_password
from app.db.base import utc_now
from app.db.session import SessionLocal, engine
from app.models import Record, Role, User

logger = logging.getLogger(__name__)

SAMPLE_RECORD_COUNT = 200
SAMPLE_DAYS = 30
# Server readings, like the realtime metrics but kept in their own table.
# category: (title after the server name, lowest value, highest value)
SAMPLE_CATEGORIES = {
    "cpu": ("CPU usage", 10, 95),
    "memory": ("Memory usage", 30, 90),
    "temperature": ("Temperature", 35, 80),
}


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


async def seed_records(session: AsyncSession) -> None:
    """Fill an empty records table with sample data from the last 30 days.

    Mostly owned by `user`, a few by `admin`, so "only the creator may
    edit" can be tried right away. A fixed seed gives the same values on
    every fresh start (the times follow the current date).
    """
    if await session.scalar(select(func.count()).select_from(Record)):
        return
    owners = {
        user.username: user.id
        for user in await session.scalars(
            select(User).where(User.username.in_(["user", "admin"]))
        )
    }
    rng = random.Random(42)
    now = utc_now()
    categories = list(SAMPLE_CATEGORIES)
    servers = settings.simulator_servers
    for i in range(SAMPLE_RECORD_COUNT):
        category = categories[i % len(categories)]
        title, low, high = SAMPLE_CATEGORIES[category]
        # Next server after every full round of categories, so each
        # server gets every category
        server = servers[i // len(categories) % len(servers)]
        session.add(
            Record(
                title=f"{server} {title}",
                value=round(rng.uniform(low, high), 1),
                category=category,
                recorded_at=now
                - timedelta(minutes=rng.randint(0, SAMPLE_DAYS * 24 * 60)),
                description=f"Sample record {i + 1}",
                # About one in five belongs to admin
                owner_id=owners["admin" if i % 5 == 0 else "user"],
            )
        )
    await session.commit()
    logger.info("Created %d sample records", SAMPLE_RECORD_COUNT)


async def main() -> None:
    setup_logging(settings.log_level)
    async with SessionLocal() as session:
        await seed_users(session)
        await seed_records(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
