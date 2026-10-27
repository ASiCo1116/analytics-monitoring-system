from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """All backend settings, read from environment variables.

    See .env.example for every variable and its default.
    """

    # Later files win: the root .env is shared with Docker Compose,
    # backend/.env (optional) overrides values for local development.
    # Inside the container neither file exists; Compose injects the variables.
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), extra="ignore"
    )

    database_url: str

    jwt_secret_key: str
    jwt_expire_minutes: int = 60

    seed_admin_password: str
    seed_user_password: str
    seed_viewer_password: str

    simulator_enabled: bool = True
    # NoDecode: read "a,b,c" as plain text instead of JSON, then split below
    simulator_servers: Annotated[list[str], NoDecode] = [
        "server-1",
        "server-2",
        "server-3",
    ]
    threshold_cpu: float = 90
    threshold_memory: float = 90
    threshold_temperature: float = 80
    batch_interval_seconds: float = 10
    batch_size: int = 100

    log_level: str = "INFO"
    app_timezone: str = "Asia/Taipei"

    @field_validator("simulator_servers", mode="before")
    @classmethod
    def split_servers(cls, value: object) -> object:
        if isinstance(value, str):
            return [name.strip() for name in value.split(",") if name.strip()]
        return value


settings = Settings()
