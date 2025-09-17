from celery import Celery, chain

from .utils import get_env

from . import collector
from . import trader
from . import optimizer

app = Celery(
    "trading_bot",
    broker=get_env("CELERY_BROKER_URL"),
    backend=get_env("CELERY_BACKEND_URL"),
)

app.conf.broker_connection_retry_on_startup = True


@app.task(queue="collector_queue")
def collect_data():
    collector.run()


@app.task(queue="trader_queue")
def run_trade():
    trader.run()


@app.task(queue="optimizer_queue")
def optimize_weights():
    optimizer.run()


# ------------------------------
# Coordinator: collect -> trade
# ------------------------------


@app.task(queue="collector_queue")
def collect_and_trade():
    chain(
        collect_data.si().set(queue="collector_queue"),
        run_trade.si().set(queue="trader_queue"),
    ).delay()
