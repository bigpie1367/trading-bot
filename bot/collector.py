import time
import requests

from datetime import timezone
from dateutil import parser as date_parser
from psycopg2.extras import execute_values, Json

from .utils import get_env, get_db_connection, get_logger

logger = get_logger("collector")

UPBIT_BASE_URL = "https://api.upbit.com/v1"
UPBIT_HEADERS = {"Accept": "application/json", "User-Agent": "trading-bot/collector"}
REQUEST_TIMEOUT = 10
UPSERT_PAGE_SIZE = 500


def run():
    """수집/적재 실행. 새 데이터 없으면 1초 후 한 번 재시도."""

    try:
        inserted = collect_data()
        if inserted == 0:
            time.sleep(1)
            inserted = collect_data()

        logger.info("collector upserted candles", extra={"inserted": inserted})
    except Exception:
        logger.exception("collector failed")
        raise


def collect_data():
    """마지막 ts 이후 분봉만 upsert하고 삽입/갱신된 행 수 반환."""

    market = get_env("MARKET", "KRW-BTC")
    unit = int(get_env("UNIT", "1"))
    timeframe = f"{unit}m"

    with get_db_connection() as connection:
        raw = _get_candles(market=market, unit=unit, count=200)
        rows = _serialize_candles(raw, timeframe=timeframe)

        last_ts = _get_last_candle_timestamp(connection, timeframe)
        if last_ts is not None:
            rows = [row for row in rows if row[1] >= last_ts]

        _upsert_candles(connection, rows)
        connection.commit()
        return len(rows)


# ------------------------------
# 내부 헬퍼 메서드
# ------------------------------


def _get_candles(market, unit, count=200):
    url = f"{UPBIT_BASE_URL}/candles/minutes/{unit}"
    params = {"market": market, "count": count}
    response = requests.get(
        url,
        params=params,
        headers=UPBIT_HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _serialize_candles(raw_candles, timeframe):
    rows = []
    for item in raw_candles:
        ts_utc = date_parser.isoparse(item["candle_date_time_utc"]).replace(
            tzinfo=timezone.utc
        )

        rows.append(
            (
                timeframe,
                ts_utc,
                item["opening_price"],
                item["high_price"],
                item["low_price"],
                item["trade_price"],
                item["candle_acc_trade_volume"],
                item.get("candle_acc_trade_price"),
                item.get("units_traded"),
                Json(
                    {
                        "market": item.get("market"),
                        "timestamp_kst": item.get("candle_date_time_kst"),
                        "unit": item.get("unit"),
                    }
                ),
            )
        )

    rows.sort(key=lambda r: r[1])
    return rows


def _get_last_candle_timestamp(connection, timeframe):
    """마지막 분봉의 ts 반환. 없으면 None."""

    sql = "SELECT max(ts) FROM candles WHERE timeframe = %s"
    with connection.cursor() as cursor:
        cursor.execute(sql, (timeframe,))

        row = cursor.fetchone()
        if row and row[0] is not None:
            ts = row[0]
            if ts.tzinfo is None:
                return ts.replace(tzinfo=timezone.utc)
            return ts.astimezone(timezone.utc)

    return None


def _upsert_candles(connection, rows):
    if not rows:
        return

    sql = """
        INSERT INTO candles (
            timeframe, ts, open, high, low, close, volume, quote_volume, trades_count, meta
        ) VALUES %s
        ON CONFLICT (timeframe, ts) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            quote_volume = EXCLUDED.quote_volume,
            trades_count = EXCLUDED.trades_count,
            meta = EXCLUDED.meta
        """

    with connection.cursor() as cursor:
        execute_values(cursor, sql, rows, page_size=UPSERT_PAGE_SIZE)
