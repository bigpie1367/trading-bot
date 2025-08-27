from celery import Celery

from . import collector
from . import trader
from . import optimizer

app = Celery(
    "trading_bot",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/1",
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
