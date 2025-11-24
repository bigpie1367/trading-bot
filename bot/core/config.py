from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    log_level: str = "INFO"

    # Database
    database_url: str

    # Upbit
    upbit_access_key: str | None = None
    upbit_secret_key: str | None = None

    # Trading
    market: str = "KRW-BTC"
    threshold: float = 0.2
    aggressiveness: float = 0.0015
    fee_rate: float = 0.0005
    fee_buffer: float = 0.0005

    # Celery
    celery_broker_url: str | None = None
    celery_backend_url: str | None = None

    # Optimizer
    opt_initial_cash: float = 1000000.0
    opt_window: int = 200
    opt_threads: int = 4
    opt_thresholds: str = ""


settings = Settings()
