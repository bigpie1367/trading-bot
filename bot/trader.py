import uuid
from datetime import timezone
from decimal import ROUND_DOWN, Decimal

from dateutil import parser as date_parser

from bot.core.config import settings
from bot.core.context import get_db_connection, get_logger
from bot.db.storage import (
    get_recent_prices,
    get_recent_weights,
    insert_order,
    insert_trade,
)
from bot.exchange.upbit import (
    fetch_account_balances,
    fetch_order,
    place_buy_limit,
    place_sell_limit,
    round_price_to_tick,
)
from bot.strategies.signal import ensemble_signal

logger = get_logger("trader")


def run():
    try:
        executed = run_trade()
        if executed:
            logger.info("trade executed", extra=executed)
        else:
            logger.info("no trade signal")
    except Exception:
        logger.exception("trader failed")
        raise


def run_trade():
    market = settings.market
    threshold = settings.threshold
    aggressiveness = settings.aggressiveness

    prices = get_recent_prices("1m", limit=200)
    if len(prices) < 3:
        return None

    last_price = prices[-1]

    # 전략 기준 매수/매도 여부 판단
    weights = get_recent_weights()

    score = ensemble_signal(prices, weights)
    if score >= threshold:
        return _execute_buy(market, last_price, aggressiveness)
    elif score <= -threshold:
        return _execute_sell(market, last_price, aggressiveness)

    return None


# ------------------------------
# 내부 헬퍼 메서드
# ------------------------------


def _execute_buy(market, last_price, aggressiveness):
    """매수가 계산 및 주문"""

    # 가용 잔고 계산 및 최소 주문 금액 확인
    balances = fetch_account_balances()
    balance = _parse_available_balance(balances, "KRW")
    if balance <= 5000.0:
        return None

    # 목표 매수 가격 계산
    target_price = round_price_to_tick(last_price * (1 + aggressiveness), mode="up")

    # 간단 수량 계산(수수료/버퍼 반영, 8자리 내림) 및 최소 주문금액 확인
    volume = _calc_buy_volume(balance, target_price)
    if volume <= 0:
        return None
    if target_price * volume <= 5000.0:
        return None

    # 지정가 매수 주문 전송 및 기록
    identifier = str(uuid.uuid4())
    response = place_buy_limit(market, target_price, volume, identifier)
    _record_order_and_trades("buy", target_price, volume, response)

    return {
        "side": "buy",
        "price": target_price,
        "volume": volume,
        "response": response,
    }


def _execute_sell(market, last_price, aggressiveness):
    """매도가 계산 및 주문"""

    # 가용 잔고 계산
    balances = fetch_account_balances()
    balance = _parse_available_balance(balances, market.split("-")[-1])
    if balance <= 0:
        return None

    # 목표 매도 가격 계산
    target_price = round_price_to_tick(last_price * (1 - aggressiveness), mode="down")

    # 최소 주문 금액 충족 검사: 보유 코인 가치가 5,000 이하면 주문 불가
    if balance * target_price <= 5000.0:
        return None

    # 보유 코인 전량 매도 및 기록
    identifier = str(uuid.uuid4())
    response = place_sell_limit(market, target_price, balance, identifier)
    _record_order_and_trades("sell", target_price, balance, response)

    return {
        "side": "sell",
        "price": target_price,
        "volume": balance,
        "response": response,
    }


def _parse_available_balance(balances, currency):
    """해당 통화의 가용잔고 반환"""

    free, locked = 0.0, 0.0
    for b in balances:
        if b.get("currency") == currency:
            free = _to_float(b.get("balance", 0.0), 0.0)
            locked = _to_float(b.get("locked", 0.0), 0.0)

            break

    return max(0.0, free - locked)


def _calc_buy_volume(balance_krw: float, target_price: float) -> float:
    """가용 KRW와 목표가로 매수 수량을 간단히 계산(수수료/버퍼 반영, 소수 8자리 내림)."""
    try:
        fee_rate = settings.fee_rate
    except Exception:
        fee_rate = 0.0005

    try:
        fee_buffer = settings.fee_buffer
    except Exception:
        fee_buffer = 0.0005

    effective_unit_cost = target_price * (1.0 + fee_rate + fee_buffer)
    if effective_unit_cost <= 0:
        return 0.0

    raw_volume = balance_krw / effective_unit_cost
    vol = Decimal(str(raw_volume)).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
    return float(vol)


def _record_order_and_trades(side, price, quantity, response):
    order_uuid = response.get("uuid") if isinstance(response, dict) else None
    exchange_meta = response if isinstance(response, dict) else {}

    with get_db_connection() as connection:
        try:
            order_id = insert_order(
                connection=connection,
                side=side,
                price=price,
                quantity=quantity,
                status="new",
                exchange_order_id=order_uuid,
                meta=exchange_meta,
            )

            connection.commit()

            if order_uuid:
                detail = fetch_order(order_uuid)

                trades = detail.get("trades", []) or []
                for t in trades:
                    data = _serialize_trade(t, order_id)
                    insert_trade(connection=connection, **data)

            connection.commit()
        except Exception:
            connection.rollback()
            raise


def _serialize_trade(raw_trade, order_id):
    data = {
        "order_id": order_id,
        "executed_at": (
            lambda dt: (
                dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            )
        )(date_parser.isoparse(raw_trade.get("created_at"))),
        "price": _to_float(raw_trade.get("price")),
        "quantity": _to_float(raw_trade.get("volume")),
        "fee": _to_float(raw_trade.get("fee"), 0.0),
        "fee_asset": raw_trade.get("fee_currency"),
        "slippage": None,
        "meta": raw_trade,
    }

    return data


def _to_float(value, default=0.0):
    try:
        return float(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default
