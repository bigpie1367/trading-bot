from celery.schedules import crontab

from .tasks import app

celery_app = app

app.conf.beat_schedule = {
    # 매 분 정각: 데이터 수집 후 트레이딩
    "collect-then-trade-every-minute": {
        "task": "bot.tasks.collect_and_trade",
        "schedule": crontab(minute="*"),
        "options": {"queue": "collector_queue"},
    },
    # 매일 01:00: 트레이딩 모델 최적화
    "run-optimizer-every-day": {
        "task": "bot.tasks.start_optimization",
        "schedule": crontab(minute=0, hour=1),
        "options": {"queue": "optimizer_queue"},
    },
}

app.conf.timezone = "Asia/Seoul"
