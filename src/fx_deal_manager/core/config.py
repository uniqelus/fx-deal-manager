from pydantic_settings import BaseSettings, SettingsConfigDict

from fx_deal_manager.core.logging import LogLevel


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "Foreign Exchange Deal Manager"
    app_version: str = "0.1.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: LogLevel = "INFO"

    database_url: str = "postgresql+asyncpg://fx:fx_password@localhost:5433/fx_deal_manager"
    jwt_issuer: str = "http://localhost:8083"
    jwks_url: str = "http://localhost:8083/.well-known/jwks.json"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    auto_migrate: bool = True

    idp_base_url: str = "http://localhost:8083"
    position_auth_client_id: str | None = None
    position_auth_client_secret: str | None = None
    position_auth_scope: str = "fx-dealing:read fx-dealing:write"
    position_auth_required: bool = True

    position_system_url: str | None = None
    position_send_retries: int = 3
    position_send_backoff_seconds: float = 0.5

    payment_save_fault_after: int | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def effective_log_level(self) -> LogLevel:
        return "DEBUG" if self.debug else self.log_level


settings = Settings()
