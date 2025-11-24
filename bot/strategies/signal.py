import numpy as np


def ensemble_signal(prices, weights):
    signals = {
        "trend": _sig_trend(prices),
        "momentum": _sig_momentum(prices, period=10),
        "swing": _sig_swing(prices),
        "scalping": _sig_scalping(prices),
        "day": _sig_day(prices),
        "price_action": _sig_price_action(prices),
        "rsi": _sig_rsi(prices),
        "bollinger": _sig_bollinger(prices),
        "macd": _sig_macd(prices),
    }

    return sum(weights.get(k, 0) * signals.get(k, 0) for k in weights)


# ------------------------------
# 전략 구현
# ------------------------------


def _sig_trend(prices):
    """단순 추세: 직전 가격 대비 상승/하락"""

    if len(prices) < 2:
        return 0

    return 1 if prices[-1] > prices[-2] else -1


def _sig_momentum(prices, period=10):
    """모멘텀: N일 전 가격 대비 현재 가격"""

    if len(prices) <= period:
        return 0

    return 1 if prices[-1] - prices[-(period + 1)] > 0 else -1


def _sig_swing(prices, short_period=5, long_period=20):
    """스윙: 단기/장기 이동평균 크로스오버"""

    if len(prices) < max(short_period, long_period):
        return 0

    return (
        1 if float(np.mean(prices[-short_period:])) > float(np.mean(prices[-long_period:])) else -1
    )


def _sig_scalping(prices, lookback=10):
    """스캘핑: 단기 변동성 돌파 전략"""

    if len(prices) < lookback + 1:
        return 0

    recent = prices[-lookback - 1 : -1]
    volatility = float(np.std(recent))

    if volatility == 0:
        return 0

    last_change = prices[-1] - prices[-2]
    threshold = volatility * 0.5

    if last_change > threshold:
        return 1
    if last_change < -threshold:
        return -1

    return 0


def _sig_day(prices, lookback=20):
    """일중 변동성 기반 전략"""

    if len(prices) < lookback:
        return 0

    recent = prices[-lookback:]
    volatility = float(np.std(recent))
    mean_price = float(np.mean(recent))

    if mean_price == 0:
        return 0

    volatility_ratio = volatility / mean_price

    # 낮은 변동성: 추세 추종
    if volatility_ratio < 0.02:
        return 1 if prices[-1] > prices[-2] else -1

    # 높은 변동성: 역추세 (평균 회귀)
    if volatility_ratio > 0.05:
        return -1 if prices[-1] > mean_price else 1

    return 0


def _sig_price_action(prices):
    """프라이스 액션: 신고점/신저점 돌파"""

    if len(prices) < 3:
        return 0

    last = prices[-1]
    prev_max = float(np.max(prices[:-1]))
    prev_min = float(np.min(prices[:-1]))

    if last > prev_max:
        return 1
    if last < prev_min:
        return -1

    return 0


def _sig_rsi(prices, period=14):
    """RSI: 과매수/과매도 지표"""

    if len(prices) <= period:
        return 0

    gains = []
    losses = []

    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    if len(gains) < period:
        return 0

    avg_gain = float(np.mean(gains[-period:]))
    avg_loss = float(np.mean(losses[-period:]))

    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

    # RSI < 30: 과매도 → 매수
    if rsi < 30:
        return 1
    # RSI > 70: 과매수 → 매도
    if rsi > 70:
        return -1

    return 0


def _sig_bollinger(prices, period=20, num_std=2):
    """Bollinger Bands: 밴드 이탈 전략"""

    if len(prices) < period:
        return 0

    recent = prices[-period:]
    middle = float(np.mean(recent))
    std = float(np.std(recent))

    upper = middle + num_std * std
    lower = middle - num_std * std

    last_price = prices[-1]

    # 하단 밴드 근처 → 매수
    if last_price <= lower:
        return 1
    # 상단 밴드 근처 → 매도
    if last_price >= upper:
        return -1

    return 0


def _sig_macd(prices, fast=12, slow=26, signal=9):
    """MACD: 이동평균 수렴확산 지표"""

    if len(prices) < slow + signal:
        return 0

    def _ema(data, period):
        """지수 이동평균 계산"""
        if len(data) < period:
            return float(np.mean(data))

        multiplier = 2 / (period + 1)
        ema_values = [float(np.mean(data[:period]))]

        for price in data[period:]:
            ema_values.append((price - ema_values[-1]) * multiplier + ema_values[-1])

        return ema_values[-1]

    ema_fast = _ema(prices, fast)
    ema_slow = _ema(prices, slow)

    macd_line = ema_fast - ema_slow

    # MACD 라인의 EMA를 시그널 라인으로 사용
    # 간단히 최근 N개 MACD 값의 평균으로 근사
    if len(prices) < slow + signal + 10:
        return 0

    macd_history = []
    for i in range(len(prices) - slow - signal, len(prices)):
        if i < slow:
            continue
        f = _ema(prices[: i + 1], fast)
        s = _ema(prices[: i + 1], slow)
        macd_history.append(f - s)

    if len(macd_history) < signal:
        return 0

    signal_line = float(np.mean(macd_history[-signal:]))

    # MACD > Signal → 매수
    if macd_line > signal_line:
        return 1
    # MACD < Signal → 매도
    if macd_line < signal_line:
        return -1

    return 0
