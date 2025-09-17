import uuid
import hashlib
import requests
import jwt

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN
from urllib.parse import urlencode

from .utils import get_env


UPBIT_API_BASE = "https://api.upbit.com"
UPBIT_API_HEADER = {
    "Accept": "application/json",
    "User-Agent": "trading-bot/bot",
    "Content-Type": "application/json; charset=utf-8",
}


def fetch_recent_candles(market, unit=1, count=200):
    """UPbit API로부터 최근 캔들 데이터 조회"""

    url = f"{UPBIT_API_BASE}/v1/candles/minutes/{unit}"

    res = requests.get(
        url,
        params={"market": market, "count": count},
        headers=UPBIT_API_HEADER,
        timeout=10,
    )
    res.raise_for_status()
    return res.json()


def fetch_account_balances():
    """계좌 잔고 조회"""

    url = f"{UPBIT_API_BASE}/v1/accounts"

    headers = {
        **UPBIT_API_HEADER,
        **_make_auth_headers(),
    }

    res = requests.get(url, headers=headers, timeout=10)
    res.raise_for_status()
    return res.json()


def round_price_to_tick(price, mode="down"):
    """호가단위에 맞춰 반올림."""

    p = float(price)

    tick = _get_tick_size(p)
    if mode == "up":
        return float(((int((p + tick - 1e-12) / tick)) * tick))
    if mode == "nearest":
        return float(round(p / tick) * tick)

    return float(int(p / tick) * tick)


def place_buy_limit(market, price, volume, identifier):
    """지정가 매수 주문"""

    if price <= 0 or volume <= 0:
        raise ValueError("Price and volume must be greater than 0")

    url = f"{UPBIT_API_BASE}/v1/orders"
    params = {
        "market": market,
        "side": "bid",
        "ord_type": "limit",
        "price": _format_price(price),
        "volume": _format_volume(volume),
        "identifier": identifier,
    }
    query_string = urlencode(params)
    headers = {
        **UPBIT_API_HEADER,
        **_make_auth_headers(query_string=query_string),
    }

    res = requests.post(url, data=query_string, headers=headers, timeout=10)
    if not res.ok:
        raise RuntimeError(f"Upbit buy order failed: {res.status_code} {res.text}")

    return res.json()


def place_sell_limit(market, price, volume, identifier):
    """지정가 매도 주문"""

    if price <= 0 or volume <= 0:
        raise ValueError("Price and volume must be greater than 0")

    url = f"{UPBIT_API_BASE}/v1/orders"
    params = {
        "market": market,
        "side": "ask",
        "ord_type": "limit",
        "price": _format_price(price),
        "volume": _format_volume(volume),
        "identifier": identifier,
    }
    query_string = urlencode(params)
    headers = {
        **UPBIT_API_HEADER,
        **_make_auth_headers(query_string=query_string),
    }

    res = requests.post(url, json=params, headers=headers, timeout=10)
    if not res.ok:
        raise RuntimeError(f"Upbit sell order failed: {res.status_code} {res.text}")

    return res.json()


def fetch_order(order_uuid):
    """주문 상세 조회"""

    url = f"{UPBIT_API_BASE}/v1/order"
    params = {"uuid": order_uuid}
    qs = urlencode(params)
    headers = {
        **UPBIT_API_HEADER,
        **_make_auth_headers(query_string=qs),
    }

    res = requests.get(url, params=params, headers=headers, timeout=10)
    res.raise_for_status()
    return res.json()


# ------------------------------
# 내부 헬퍼 메서드
# ------------------------------


def _make_auth_headers(params=None, query_string=None):
    access_key = get_env("UPBIT_ACCESS_KEY")
    secret_key = get_env("UPBIT_SECRET_KEY")

    payload = {
        "access_key": access_key,
        "nonce": str(uuid.uuid4()),
        "exp": datetime.utcnow() + timedelta(seconds=30),
    }

    if query_string is not None:
        m = hashlib.sha512()
        m.update(query_string.encode())
        query_hash = m.hexdigest()
        payload.update({"query_hash": query_hash, "query_hash_alg": "SHA512"})
    elif params:
        m = hashlib.sha512()
        m.update(urlencode(params).encode())
        query_hash = m.hexdigest()
        payload.update({"query_hash": query_hash, "query_hash_alg": "SHA512"})

    token = jwt.encode(payload, secret_key, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def _format_price(price):
    p = Decimal(str(price))
    tick = Decimal(str(_get_tick_size(price)))
    q = p.quantize(tick, rounding=ROUND_DOWN)
    decimals = max(0, -tick.as_tuple().exponent)
    return f"{q:.{decimals}f}"


def _format_volume(volume):
    return f"{Decimal(str(volume)).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN):.8f}"


def _get_tick_size(price):
    p = float(price)
    if p >= 2_000_000:
        return 1000
    if p >= 1_000_000:
        return 500
    if p >= 500_000:
        return 100
    if p >= 100_000:
        return 50
    if p >= 10_000:
        return 10
    if p >= 1_000:
        return 5
    if p >= 100:
        return 1
    if p >= 10:
        return 0.1

    return 0.01
