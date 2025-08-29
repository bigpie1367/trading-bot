import os
import logging
import psycopg2

from pythonjsonlogger import jsonlogger


_json_formatter = jsonlogger.JsonFormatter(
    "%(asctime)s %(levelname)s %(name)s %(message)s %(filename)s %(lineno)d"
)
_stream_handler = logging.StreamHandler()
_stream_handler.setFormatter(_json_formatter)


def get_logger(name="trading-bot", level=None):
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO")

    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.addHandler(_stream_handler)

    logger.setLevel(level)
    logger.propagate = False
    return logger


def get_env(name, default=None):
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Required environment variable not set: {name}")

    return value


def get_db_connection():
    try:
        return psycopg2.connect(get_env("DATABASE_URL"))
    except (RuntimeError, psycopg2.Error) as e:
        raise RuntimeError("Failed to connect to database") from e
