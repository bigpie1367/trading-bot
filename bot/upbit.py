import requests


UPBIT_API_BASE = "https://api.upbit.com"


def fetch_recent_candles(market, unit=1, count=200):
    """UPbit API로부터 최근 캔들 데이터 조회"""
    url = f"{UPBIT_API_BASE}/v1/candles/minutes/{unit}"

    res = requests.get(
        url,
        params={"market": market, "count": count},
        headers={"Accept": "application/json", "User-Agent": "trading-bot/collector"},
        timeout=10,
    )
    res.raise_for_status()
    return res.json()
