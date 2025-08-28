from celery import Celery

from .utils import get_env

from . import collector
from . import trader
from . import optimizer

app = Celery(
    "trading_bot",
    broker=get_env("CELERY_BROKER_URL"),
    backend=get_env("CELERY_RESULT_BACKEND_URL"),
)


@app.task(queue="collector_queue")
def collect_data():
    collector.run()


@app.task(queue="trader_queue")
def run_trade():
    trader.run()


@app.task(queue="optimizer_queue")
def optimize_weights():
    optimizer.run()
