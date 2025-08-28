from datetime import timezone
from psycopg2.extras import Json, execute_values

from .utils import get_db_connection


UPSERT_PAGE_SIZE = 200


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


def get_recent_timestamp(connection, timeframe):
    sql = """
        SELECT ts
        FROM candles
        WHERE timeframe = %s
        ORDER BY ts DESC
        LIMIT 1
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, (timeframe,))
        row = cursor.fetchone()
        if not row:
            return None

        ts = row[0]
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)

        return ts.astimezone(timezone.utc)


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


def get_latest_weights():
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

    params = row[0]
    if "weights" not in params or not isinstance(params["weights"], dict):
        return {
            "trend": 0,
            "momentum": 0,
            "swing": 0,
            "scalping": 0,
            "day": 0,
            "price_action": 0,
        }

    return params["weights"]


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

        inserted_id = cursor.fetchone()[0]
        return inserted_id


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
