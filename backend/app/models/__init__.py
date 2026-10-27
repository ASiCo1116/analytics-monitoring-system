# Import every model so Base.metadata knows all tables (used by Alembic and tests)
from app.models.metric import Metric, MetricName
from app.models.record import Record
from app.models.system_log import LogLevel, SystemLog
from app.models.user import Role, User

__all__ = ["LogLevel", "Metric", "MetricName", "Record", "Role", "SystemLog", "User"]
