from datetime import UTC, datetime
from typing import Annotated

from pydantic import PlainSerializer


def _to_utc_string(value: datetime) -> str:
    # The database stores naive UTC; mark it as UTC before serializing
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


# Output type for every datetime in a response: ISO 8601 ending in "Z".
# Pydantic would otherwise serialize a naive datetime without any time zone.
UtcDatetime = Annotated[
    datetime,
    PlainSerializer(_to_utc_string, return_type=str, when_used="json"),
]
