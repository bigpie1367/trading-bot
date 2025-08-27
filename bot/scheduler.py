from .tasks import app


app.conf.beat_schedule = {
    "run-collector-every-minute": {
        "task": "tasks.collect_data",
        "schedule": 60.0,
        "options": {"queue": "collector_queue"},
    },
    "run-trader-every-minute": {
        "task": "tasks.run_trade",
        "schedule": 60.0,
        "options": {"queue": "trader_queue"},
    },
    "run-optimizer-every-day": {
        "task": "tasks.optimize_weights",
        "schedule": 86400.0,
        "options": {"queue": "optimizer_queue"},
    },
}

app.conf.timezone = "Asia/Seoul"
