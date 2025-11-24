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
    opt_coarse_step: float = 0.2  # 1단계 grid step
    opt_fine_step: float = 0.05  # 2단계 grid step
    opt_top_percent: float = 0.1  # 2단계로 넘어갈 상위 비율
    opt_early_stop_threshold: float = -0.3  # early stopping 손실률 임계값
    opt_early_stop_candles: int = 50  # early stopping 판단 캔들 수


settings = Settings()
