import uuid
from enum import StrEnum

from sqlalchemy import Enum, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Role(StrEnum):
    admin = "admin"
    user = "user"
    viewer = "viewer"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    # UUIDv7 is time-ordered, so inserts into the clustered primary key stay nearly sequential.
    # SQLAlchemy 2.1 maps Uuid to MariaDB's native UUID type (10.7+).
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role, name="user_role"), default=Role.user)
    is_active: Mapped[bool] = mapped_column(default=True)
