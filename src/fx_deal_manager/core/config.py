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

    @property
    def effective_log_level(self) -> LogLevel:
        return "DEBUG" if self.debug else self.log_level


settings = Settings()
