import logging

import psycopg
from pythonjsonlogger import jsonlogger

from bot.core.config import settings

_json_formatter = jsonlogger.JsonFormatter(
    "%(asctime)s %(levelname)s %(name)s %(message)s %(filename)s %(lineno)d"
)
_stream_handler = logging.StreamHandler()
_stream_handler.setFormatter(_json_formatter)


def get_logger(name="trading-bot", level=None):
    if level is None:
        level = settings.log_level

    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.addHandler(_stream_handler)

    logger.setLevel(level)
    logger.propagate = False
    return logger


def get_db_connection():
    try:
        return psycopg.connect(settings.database_url)
    except (RuntimeError, psycopg.Error) as e:
        raise RuntimeError("Failed to connect to database") from e
