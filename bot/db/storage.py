from datetime import timezone

from psycopg.types.json import Json

from bot.core.context import get_db_connection

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
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        cursor.executemany(sql, rows)


def load_ohlcv(timeframe, months):
    sql = """
        SELECT open, high, low, close, volume
        FROM candles
        WHERE timeframe = %s AND ts >= now() - make_interval(months => %s)
        ORDER BY ts ASC
    """

    with get_db_connection() as connection, connection.cursor() as cursor:
        cursor.execute(sql, (timeframe, months))
        rows = cursor.fetchall()

    # 딕셔너리 리스트 반환
    return [
        {
            "open": float(r[0]),
            "high": float(r[1]),
            "low": float(r[2]),
            "close": float(r[3]),
            "volume": float(r[4]),
        }
        for r in rows
    ]


# ------------------------------
# Optimizer
# ------------------------------


def get_recent_weights():
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

    if not row:
        return {
            "trend": 0.2,
            "momentum": 0.2,
            "swing": 0.2,
            "scalping": 0.15,
            "day": 0.15,
            "price_action": 0.1,
        }

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


def save_optimizer_result(params, metrics, mark_best):
    sql_reset = """
        UPDATE optimizer_results
        SET is_best = FALSE
        WHERE is_best = TRUE
    """

    sql_insert = """
        INSERT INTO optimizer_results (params, metrics, is_best)
        VALUES (%s, %s, %s)
    """

    params_json = {
        "weights": params.get("weights", {}),
        "threshold": params.get("threshold"),
    }

    metrics_json = {
        "final_equity": metrics.get("final_equity"),
        "total_return": metrics.get("total_return"),
        "max_drawdown": metrics.get("max_drawdown"),
        "sharpe": metrics.get("sharpe"),
        "win_rate": metrics.get("win_rate"),
        "num_trades": metrics.get("num_trades"),
    }

    with get_db_connection() as connection, connection.cursor() as cursor:
        if mark_best:
            # 기존 best 결과 잠금
            cursor.execute("SELECT id FROM optimizer_results WHERE is_best = TRUE FOR UPDATE")
            cursor.execute(sql_reset)

        cursor.execute(sql_insert, (Json(params_json), Json(metrics_json), mark_best))
        connection.commit()


# ------------------------------
# Trades
# ------------------------------


def insert_order(connection, side, price, quantity, status, exchange_order_id, meta):
    sql = """
        INSERT INTO orders (side, price, quantity, status, exchange_order_id, meta)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """

    with connection.cursor() as cursor:
        cursor.execute(
            sql,
            (side, price, quantity, status, exchange_order_id, Json(meta)),
        )

        row = cursor.fetchone()
        return row[0]


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
