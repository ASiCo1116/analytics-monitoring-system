import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Double, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Record(TimestampMixin, Base):
    """A data record entered manually by a user."""

    __tablename__ = "records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    value: Mapped[float] = mapped_column(Double)
    # Free text; no separate category table
    category: Mapped[str] = mapped_column(String(50), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    # When the data itself happened (naive UTC); used for filtering and analytics
    recorded_at: Mapped[datetime] = mapped_column(index=True)
    # Creator; decides who may update or delete the record
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
