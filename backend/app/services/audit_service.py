"""Audit events stored in the system_logs table."""

import logging
import uuid

from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.models import LogLevel, SystemLog

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 500  # system_logs.message is VARCHAR(500)


async def log(
    action: str,
    message: str,
    *,
    level: LogLevel = LogLevel.INFO,
    user_id: uuid.UUID | None = None,
    ip_address: str | None = None,
) -> None:
    """Write one audit event. Never raises.

    Uses its own session, so the event is kept even when the caller's
    transaction rolls back (e.g. a failed login), and a failure here never
    breaks the caller's request: it is only reported to stdout.
    """
    try:
        async with SessionLocal() as session:
            session.add(
                SystemLog(
                    level=level,
                    action=action,
                    message=message[:MAX_MESSAGE_LENGTH],
                    user_id=user_id,
                    ip_address=ip_address,
                )
            )
            await session.commit()
    except OperationalError as exc:
        # Database unreachable: expected while it is down and may repeat
        # every few seconds (failed metric writes), so one line, no traceback
        logger.error(
            "Could not write system log %s: %s (%s)", action, message, exc.orig
        )
    except Exception:
        # Deliberately broad: audit logging must not affect the request
        logger.exception("Could not write system log %s: %s", action, message)
