import time

from datetime import timezone
from dateutil import parser as date_parser
from psycopg.types.json import Json

from .utils import get_env, get_db_connection, get_logger
from .upbit import fetch_recent_candles
from .storage import get_recent_timestamp, insert_candles

logger = get_logger("collector")


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
        raw = fetch_recent_candles(market=market, unit=unit)
        rows = _serialize_candles(raw, timeframe=timeframe)

        last_ts = get_recent_timestamp(connection, timeframe)
        if last_ts is not None:
            rows = [row for row in rows if row[1] > last_ts]

        insert_candles(connection, rows)
        connection.commit()
        return len(rows)


# ------------------------------
# 내부 헬퍼 메서드
# ------------------------------


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
