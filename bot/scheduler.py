from celery.schedules import crontab

from .tasks import app


app.conf.beat_schedule = {
    # 매 분 정각: 수집 후 약간 지연하여 트레이딩 실행
    "collect-then-trade-every-minute": {
        "task": "bot.tasks.collect_and_trade",
        "schedule": crontab(minute="*"),
        "options": {"queue": "collector_queue"},
    },
    # 매일 00:05
    "run-optimizer-every-day": {
        "task": "bot.tasks.optimize_weights",
        "schedule": crontab(minute=5, hour=0),
        "options": {"queue": "optimizer_queue"},
    },
}

app.conf.timezone = "Asia/Seoul"
