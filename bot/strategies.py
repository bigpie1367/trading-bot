import numpy as np


def ensemble_signal(prices, weights):
    signals = {
        "trend": _sig_trend(prices),
        "momentum": _sig_momentum(prices),
        "swing": _sig_swing(prices),
        "scalping": _sig_scalping(prices),
        "day": _sig_day(prices),
        "price_action": _sig_price_action(prices),
    }

    return sum(weights.get(k, 0) * signals.get(k, 0) for k in weights)


# ------------------------------
# 전략 구현
# ------------------------------


def _sig_trend(prices):
    if len(prices) < 2:
        return 0

    return 1 if prices[-1] > prices[-2] else -1


def _sig_momentum(prices, period=5):
    if len(prices) <= period:
        return 0
    return 1 if prices[-1] - prices[-period] > 0 else -1


def _sig_swing(prices, s=5, l=20):
    if len(prices) < max(s, l):
        return 0
    return 1 if float(np.mean(prices[-s:])) > float(np.mean(prices[-l:])) else -1


def _sig_scalping(prices, take_ratio=0.001, stop_ratio=0.001):
    if len(prices) < 2:
        return 0
    prev = float(prices[-2])
    last = float(prices[-1])
    if prev <= 0:
        return 0
    change = (last - prev) / prev
    if change >= take_ratio:
        return 1
    if change <= -stop_ratio:
        return -1
    return 0


def _sig_day(prices):
    if len(prices) < 2:
        return 0
    return 1 if prices[-1] > prices[-2] else -1


def _sig_price_action(prices):
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
