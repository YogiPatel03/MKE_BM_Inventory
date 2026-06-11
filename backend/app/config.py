from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str
    database_url_sync: str

    # Auth
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    # Telegram
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    telegram_coordinator_chat_id: str = ""
    # Optional forum topic thread ID for coordinator alerts (use /whereami inside the Inventory topic)
    telegram_coordinator_thread_id: str = ""
    # JSON mapping of group name → message_thread_id, e.g. {"SHISHU_MANDAL":12,"GROUP_1":34}
    telegram_group_topic_thread_ids: str = ""

    # App
    app_name: str = "Cabinet Inventory"
    app_timezone: str = "America/Chicago"
    environment: str = "development"
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"

    # Sentry
    sentry_dsn: str = ""

    # Internal job auth — used by GitHub Actions cron → backend HTTP triggers
    cron_secret: str = ""

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token)


settings = Settings()
