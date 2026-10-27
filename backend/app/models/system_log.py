import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utc_now


class LogLevel(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class SystemLog(Base):
    """Audit event (login, record changes, role changes, errors, ...)."""

    __tablename__ = "system_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    level: Mapped[LogLevel] = mapped_column(Enum(LogLevel, name="log_level"), index=True)
    # e.g. login_failed, record_create, role_change (see design.md)
    action: Mapped[str] = mapped_column(String(50), index=True)
    message: Mapped[str] = mapped_column(String(500))
    # Empty when the actor is unknown, e.g. a failed login for a non-existent username
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    ip_address: Mapped[str | None] = mapped_column(String(45))  # long enough for IPv6
    created_at: Mapped[datetime] = mapped_column(default=utc_now, index=True)
