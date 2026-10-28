from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """All backend settings, read from environment variables.

    See .env.example for every variable and its default.
    """

    # The root .env, shared with Docker Compose (the backend runs from
    # backend/). Inside the container the file does not exist; Compose
    # injects the variables. Environment variables win over the file.
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    # The same account the MariaDB container creates on first start
    mariadb_user: str
    mariadb_password: str
    mariadb_database: str
    # `db` inside Docker; the local pixi tasks set localhost
    db_host: str = "db"
    db_port: int = 3306

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

    @property
    def database_url(self) -> str:
        """SQLAlchemy connection string built from the parts above.

        URL.create escapes characters such as "@" or "/" in the password.
        """
        url = URL.create(
            "mysql+asyncmy",
            username=self.mariadb_user,
            password=self.mariadb_password,
            host=self.db_host,
            port=self.db_port,
            database=self.mariadb_database,
        )
        return url.render_as_string(hide_password=False)


settings = Settings()
