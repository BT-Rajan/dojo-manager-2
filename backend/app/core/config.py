from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (prefix ``DOJO_``) or ``.env``."""

    model_config = SettingsConfigDict(env_prefix="DOJO_", env_file=".env", extra="ignore")

    app_name: str = "Dojo Manager"
    environment: str = Field(default="development", pattern="^(development|test|production)$")
    # Calendar days, reports and "today" follow the academy's local time.
    timezone: str = "Asia/Kuwait"

    # MySQL connection. asyncmy is the async driver; PyMySQL is used by Alembic.
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "dojo"
    db_password: SecretStr = SecretStr("")
    db_name: str = "dojo"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 1800
    db_echo: bool = False

    # Where the server listens (used by start.sh and the pm2 app "dojo"). 0.0.0.0 makes it
    # reachable from other machines; use 127.0.0.1 behind a reverse proxy.
    host: str = "0.0.0.0"  # noqa: S104 - intended: the academy reaches it over the network
    port: int = Field(default=8090, ge=1, le=65535)

    # Built React app served at / by the API process (frontend/dist when not set).
    frontend_dist: str | None = None

    # Sessions
    session_cookie_name: str = "dojo_session"
    session_ttl_hours: int = 12
    cookie_secure: bool = True
    cors_origins: list[str] = ["http://localhost:5173"]

    # Login throttling (per client IP and per username)
    login_max_attempts: int = 10
    login_window_seconds: int = 300

    # Member and parent portal: sign-in by mobile number and a 4-digit WhatsApp code.
    portal_cookie_name: str = "dojo_portal"
    portal_session_ttl_hours: int = 24 * 14
    portal_code_ttl_seconds: int = 300
    portal_code_max_attempts: int = 5
    # Key for hashing sign-in codes. Set it in production; when empty, a random key is made at
    # start-up (codes then stop working across restarts).
    portal_secret: SecretStr | None = None
    # WhatsApp / SMS provider. "console": development and tests; messages are logged and the
    # portal shows the last code on screen outside production.
    messaging_backend: str = Field(default="console", pattern="^(console)$")

    # Initial owner account, created by ``python -m app.seed`` when no users exist.
    bootstrap_owner_username: str = "owner"
    bootstrap_owner_password: SecretStr | None = None

    def frontend_dist_path(self) -> Path:
        if self.frontend_dist:
            return Path(self.frontend_dist)
        return Path(__file__).resolve().parents[3] / "frontend" / "dist"

    def database_url(self, driver: str = "asyncmy") -> URL:
        # URL.create takes the raw values, so any password works (#, spaces, quotes, @ ...);
        # no hand-made escaping that the driver might decode differently.
        return URL.create(
            f"mysql+{driver}",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            query={"charset": "utf8mb4"},
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
