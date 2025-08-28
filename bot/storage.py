from datetime import datetime, timezone
from psycopg2.extras import Json, execute_values

from .utils import get_db_connection


# ------------------------------
# Candles
# ------------------------------


def get_recent_prices(timeframe, limit=200):
    sql = """
        SELECT close
        FROM candles
        WHERE timeframe = %s
        ORDER BY ts DESC
        LIMIT %s
    """

    with get_db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(sql, (timeframe, limit))
        rows = cursor.fetchall()

    return [float(r[0]) for r in rows][::-1]


def get_recent_candle(connection, timeframe):
    sql = "SELECT max(ts) FROM candles WHERE timeframe = %s"

    with connection.cursor() as cursor:
        cursor.execute(sql, (timeframe,))
        row = cursor.fetchone()
        if row and row[0] is not None:
            return row[0]

        return None


def insert_candles(connection, rows):
    if not rows:
        return

    sql = """
        INSERT INTO candles (
            timeframe, ts, open, high, low, close, volume, quote_volume, meta
        ) VALUES %s
        ON CONFLICT (timeframe, ts) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            quote_volume = EXCLUDED.quote_volume,
            meta = EXCLUDED.meta
        """

    with connection.cursor() as cursor:
        execute_values(cursor, sql, rows, page_size=UPSERT_PAGE_SIZE)


# ------------------------------
# Optimizer
# ------------------------------


def get_latest_weights(default_weights):
    sql = """
        SELECT params
        FROM optimizer_results
        WHERE is_best = TRUE
        ORDER BY created_at DESC
        LIMIT 1
    """

    with get_db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(sql)
        row = cursor.fetchone()

    weights = row[0]["params"]["weights"]
    return weights


# ------------------------------
# Trades
# ------------------------------


def insert_order(
    connection, side, order_type, price, quantity, status, exchange_order_id, meta
):
    sql = """
        INSERT INTO orders (side, order_type, price, quantity, status, exchange_order_id, meta)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """

    with connection.cursor() as cursor:
        cursor.execute(
            sql,
            (side, order_type, price, quantity, status, exchange_order_id, Json(meta)),
        )


def insert_trade(
    connection, order_id, executed_at, price, quantity, fee, fee_asset, slippage, meta
):
    sql = """
        INSERT INTO trades (order_id, executed_at, price, quantity, fee, fee_asset, slippage, meta)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """

    with connection.cursor() as cursor:
        cursor.execute(
            sql,
            (
                order_id,
                executed_at,
                price,
                quantity,
                fee,
                fee_asset,
                slippage,
                Json(meta),
            ),
        )


def get_open_orders():
    sql = """
        SELECT id, exchange_order_id, meta
        FROM orders
        WHERE status IN ('new', 'partially_filled')
          AND exchange_order_id IS NOT NULL
        ORDER BY placed_at ASC
    """

    with get_db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(sql)
        return cursor.fetchall()
