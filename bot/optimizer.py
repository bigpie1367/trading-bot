import os
import math
import numpy as np

from concurrent.futures import ThreadPoolExecutor

from .utils import get_env, get_logger
from .upbit import round_price_to_tick
from .storage import load_closes, save_optimizer_result
from .strategies import ensemble_signal


logger = get_logger("optimizer")


STRATEGY_KEYS = [
    "trend",
    "momentum",
    "swing",
    "scalping",
    "day",
    "price_action",
]

GRID_STEP = 0.1  # 가중치 전수 탐색의 기본 격자 간격(합=1.0)


def run():
    """3개월 데이터 기반 무작위 탐색으로 weights/threshold 최적화."""
    try:
        timeframe = f"{int(get_env('UNIT', '1'))}m"

        initial_cash = float(get_env("OPT_INITIAL_CASH", "1000000"))

        fee_rate = float(get_env("FEE_RATE", "0.0005"))
        fee_buffer = float(get_env("FEE_BUFFER", "0.0005"))

        aggressiveness = float(get_env("AGGRESSIVENESS", "0.0015"))

        thresholds = _generate_threshold_candidates()

        opt_window = int(get_env("OPT_WINDOW", "200"))
        max_workers = int(get_env("OPT_THREADS", str(min(8, (os.cpu_count() or 4)))))

        closes = load_closes(timeframe=timeframe, months=3)
        if len(closes) < 200:
            logger.info(
                "not enough candles for backtest; need >=200, got %d", len(closes)
            )
            return

        candidates = _generate_weight_grid(GRID_STEP)

        logger.info(
            "start optimization",
            extra={
                "timeframe": timeframe,
                "months": 3,
                "thresholds": thresholds,
                "search": "grid",
                "grid_step": GRID_STEP,
                "num_candidates": len(candidates),
                "num_candles": len(closes),
                "max_workers": max_workers,
            },
        )

        # 모든 후보에 대해 백테스트 수행 후 최적 선택
        param_list = [
            {"weights": w, "threshold": th} for w in candidates for th in thresholds
        ]
        pairs = []

        def _eval_one(p):
            return (
                _backtest(
                    closes=closes,
                    weights=p["weights"],
                    threshold=p["threshold"],
                    initial_cash=initial_cash,
                    fee_rate=fee_rate,
                    fee_buffer=fee_buffer,
                    aggressiveness=aggressiveness,
                    window=opt_window,
                ),
                p,
            )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for res in executor.map(_eval_one, param_list, chunksize=1):
                pairs.append(res)

        if not pairs:
            logger.info("no candidate evaluated")
            return

        best, best_params = max(
            pairs, key=lambda r: (r[0].get("total_return", 0), r[0].get("sharpe", 0))
        )

        save_optimizer_result(params=best_params, metrics=best, mark_best=True)

        logger.info(
            "optimization done",
            extra={
                "final_equity": best["final_equity"],
                "total_return": best["total_return"],
                "max_drawdown": best["max_drawdown"],
                "sharpe": best["sharpe"],
                "win_rate": best["win_rate"],
                "num_trades": best["num_trades"],
                "threshold": best_params.get("threshold"),
                "weights": best_params.get("weights"),
            },
        )
    except Exception:
        logger.exception("optimizer failed")
        raise


# ------------------------------
# 내부 헬퍼 메서드
# ------------------------------


def _generate_threshold_candidates():
    raw = get_env("OPT_THRESHOLDS", "").strip()
    if raw:
        return [float(x) for x in raw.split(",") if x.strip()]

    return [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5]


def _generate_weight_grid(step):
    try:
        step = float(step)
    except Exception:
        step = 0.1
    if step <= 0 or step > 1:
        step = 0.1

    units = int(round(1.0 / step))

    # 6개 전략에 대한 비음수 정수 해를 모두 생성하여 합이 units가 되도록 분배
    candidates = []
    for a in range(units + 1):
        rem_a = units - a
        for b in range(rem_a + 1):
            rem_b = rem_a - b
            for c in range(rem_b + 1):
                rem_c = rem_b - c
                for d in range(rem_c + 1):
                    rem_d = rem_c - d
                    for e in range(rem_d + 1):
                        f = rem_d - e
                        weights = [a, b, c, d, e, f]
                        w = [float(x) / float(units) for x in weights]
                        candidates.append({k: v for k, v in zip(STRATEGY_KEYS, w)})

    return candidates


def _backtest(
    closes,
    weights,
    threshold,
    initial_cash,
    fee_rate,
    fee_buffer,
    aggressiveness,
    window=200,
):
    cash_krw = float(initial_cash)
    coin_qty = 0.0

    equity_curve = []
    returns = []

    last_equity = cash_krw
    win_trades = 0
    total_trades = 0

    min_order_krw = 5000.0

    window = max(3, min(int(window), len(closes)))
    for i in range(len(closes)):
        price = float(closes[i])

        # 매 시점의 평가금액 기록
        equity = cash_krw + coin_qty * price
        equity_curve.append(equity)

        if i > 0 and last_equity > 0:
            returns.append((equity - last_equity) / last_equity)

        last_equity = equity

        # 전략 계산에 필요한 최소 캔들 수 확보 후 진행
        if i + 1 < max(3, window):
            continue

        # 최근 window개의 캔들로 시그널 계산 (현재 시점 포함)
        recent = closes[i + 1 - window : i + 1]
        score = float(ensemble_signal(recent, weights))

        # BUY
        if score >= threshold:
            if cash_krw > min_order_krw:
                target_price = round_price_to_tick(
                    price * (1.0 + aggressiveness), mode="up"
                )
                effective_unit_cost = target_price * (1.0 + fee_rate + fee_buffer)
                if effective_unit_cost > 0:
                    raw_volume = cash_krw / effective_unit_cost
                    volume = float(np.floor(raw_volume * 1e8) / 1e8)
                else:
                    volume = 0.0

                if volume > 0 and target_price * volume > min_order_krw:
                    spend = target_price * volume
                    fee = spend * fee_rate
                    cash_krw -= spend + fee
                    coin_qty += volume
                    total_trades += 1

        # SELL
        elif score <= -threshold:
            if coin_qty > 0:
                target_price = round_price_to_tick(
                    price * (1.0 - aggressiveness), mode="down"
                )
                proceed = target_price * coin_qty
                if proceed > min_order_krw:
                    fee = proceed * fee_rate
                    cash_krw += proceed - fee

                    buy_cost_basis = equity - (coin_qty * price)  # 근사치
                    after_equity = cash_krw
                    if after_equity > equity:
                        win_trades += 1

                    coin_qty = 0.0
                    total_trades += 1

    final_equity = cash_krw + coin_qty * float(closes[-1])

    total_return = (final_equity / float(initial_cash)) - 1.0
    max_dd = _max_drawdown(equity_curve)
    sharpe = _sharpe_ratio(returns)
    win_rate = (win_trades / total_trades) if total_trades > 0 else 0.0

    print(
        f"final_equity: {final_equity}, total_return: {total_return}, mdd: {max_dd}, sharpe: {sharpe}, win_rate: {win_rate}, total_trades: {total_trades}"
    )

    return {
        "final_equity": final_equity,
        "total_return": total_return,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "win_rate": win_rate,
        "num_trades": total_trades,
    }


def _max_drawdown(equity_curve):
    peak = -math.inf
    max_dd = 0.0
    for v in equity_curve:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd


def _sharpe_ratio(returns, periods_per_year=365 * 24 * 60):
    if not returns:
        return 0.0
    mean = float(np.mean(returns))
    std = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
    if std == 0.0:
        return 0.0
    # 분당 수익률을 연율화
    return math.sqrt(periods_per_year) * (mean / std)


if __name__ == "__main__":
    run()
