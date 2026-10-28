"""Display labels for the values the API uses, shared by every page."""

METRICS = {"cpu": "CPU", "memory": "記憶體", "temperature": "溫度"}
# The backend knows them too; the analytics endpoints do not return units
METRIC_UNITS = {"cpu": "%", "memory": "%", "temperature": "°C"}
ROLES = {"admin": "Admin", "user": "User", "viewer": "Viewer"}


def metric_label(metric: str) -> str:
    return METRICS.get(metric, metric)


def role_label(role: str) -> str:
    return ROLES.get(role, role)
