import math
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from bot.core.config import settings
from bot.core.context import get_logger
from bot.db.storage import load_ohlcv, save_optimizer_result
from bot.exchange.upbit import round_price_to_tick
from bot.strategies.signal import ensemble_signal

logger = get_logger("optimizer")


STRATEGY_KEYS = [
    "trend",
    "momentum",
    "swing",
    "scalping",
    "day",
    "price_action",
    "rsi",
    "bollinger",
    "macd",
]


def run():
    """2단계 Coarse-to-Fine Grid Search로 weights/threshold 최적화."""

    try:
        timeframe = "1m"
        initial_cash = settings.opt_initial_cash
        fee_rate = settings.fee_rate
        fee_buffer = settings.fee_buffer
        aggressiveness = settings.aggressiveness
        thresholds = _generate_threshold_candidates()
        opt_window = settings.opt_window
        max_workers = settings.opt_threads

        candles = load_ohlcv(timeframe=timeframe, months=3)
        if len(candles) < 200:
            logger.info(f"not enough candles for backtest; need >=200, got {len(candles)}")
            return

        logger.info(
            "start 2-stage optimization",
            extra={
                "timeframe": timeframe,
                "months": 3,
                "thresholds": thresholds,
                "coarse_step": settings.opt_coarse_step,
                "fine_step": settings.opt_fine_step,
                "top_percent": settings.opt_top_percent,
                "num_candles": len(candles),
                "max_workers": max_workers,
            },
        )

        # Stage 1: Coarse Search
        coarse_results = _run_coarse_search(
            candles=candles,
            thresholds=thresholds,
            initial_cash=initial_cash,
            fee_rate=fee_rate,
            fee_buffer=fee_buffer,
            aggressiveness=aggressiveness,
            window=opt_window,
            max_workers=max_workers,
        )

        if not coarse_results:
            logger.info("no candidate evaluated in coarse search")
            return

        # Stage 2: Fine Search around top performers
        fine_results = _run_fine_search(
            candles=candles,
            thresholds=thresholds,
            coarse_results=coarse_results,
            initial_cash=initial_cash,
            fee_rate=fee_rate,
            fee_buffer=fee_buffer,
            aggressiveness=aggressiveness,
            window=opt_window,
            max_workers=max_workers,
        )

        # Combine and select best
        all_results = coarse_results + fine_results
        best, best_params = max(
            all_results, key=lambda r: (r[0].get("total_return", 0), r[0].get("sharpe", 0))
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


def _run_coarse_search(
    candles, thresholds, initial_cash, fee_rate, fee_buffer, aggressiveness, window, max_workers
):
    """1단계: Coarse Grid Search 실행."""
    coarse_step = settings.opt_coarse_step
    candidates = _generate_weight_grid(coarse_step)

    logger.info(
        "stage 1: coarse search",
        extra={"grid_step": coarse_step, "num_candidates": len(candidates)},
    )

    param_list = [{"weights": w, "threshold": th} for w in candidates for th in thresholds]
    results = []
    total_tasks = len(param_list)

    def _eval_one(p):
        return (
            _backtest(
                candles=candles,
                weights=p["weights"],
                threshold=p["threshold"],
                initial_cash=initial_cash,
                fee_rate=fee_rate,
                fee_buffer=fee_buffer,
                aggressiveness=aggressiveness,
                window=window,
            ),
            p,
        )

    logger.info(
        "starting coarse search execution",
        extra={"total_tasks": total_tasks},
    )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for i, res in enumerate(executor.map(_eval_one, param_list, chunksize=1)):
            results.append(res)
            # Progress logging every 1000 tasks
            if (i + 1) % 1000 == 0 or (i + 1) == total_tasks:
                logger.info(
                    "coarse search progress",
                    extra={
                        "completed": i + 1,
                        "total": total_tasks,
                        "percent": round((i + 1) / total_tasks * 100, 1),
                    },
                )

    logger.info(
        "stage 1 complete",
        extra={"num_evaluated": len(results)},
    )

    return results


def _run_fine_search(
    candles,
    thresholds,
    coarse_results,
    initial_cash,
    fee_rate,
    fee_buffer,
    aggressiveness,
    window,
    max_workers,
):
    """2단계: Fine Grid Search 실행 (상위 결과 주변)."""
    fine_step = settings.opt_fine_step
    top_percent = settings.opt_top_percent

    # 상위 N% 선택 (최대 50개로 제한)
    sorted_results = sorted(
        coarse_results,
        key=lambda r: (r[0].get("total_return", 0), r[0].get("sharpe", 0)),
        reverse=True,
    )
    top_n = max(1, min(50, int(len(sorted_results) * top_percent)))
    top_results = sorted_results[:top_n]

    logger.info(
        "stage 2: fine search",
        extra={
            "grid_step": fine_step,
            "top_n": top_n,
            "top_percent": top_percent,
        },
    )

    # 상위 결과들의 가중치 주변 이웃 생성
    fine_candidates = set()
    for _, params in top_results:
        neighbors = _generate_neighbor_weights(params["weights"], fine_step)
        for neighbor in neighbors:
            fine_candidates.add(tuple(sorted(neighbor.items())))

    fine_candidates = [dict(c) for c in fine_candidates]

    logger.info(
        "fine search candidates generated",
        extra={"num_candidates": len(fine_candidates)},
    )

    param_list = [{"weights": w, "threshold": th} for w in fine_candidates for th in thresholds]
    results = []
    total_tasks = len(param_list)

    def _eval_one(p):
        return (
            _backtest(
                candles=candles,
                weights=p["weights"],
                threshold=p["threshold"],
                initial_cash=initial_cash,
                fee_rate=fee_rate,
                fee_buffer=fee_buffer,
                aggressiveness=aggressiveness,
                window=window,
            ),
            p,
        )

    logger.info(
        "starting fine search execution",
        extra={"total_tasks": total_tasks},
    )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for i, res in enumerate(executor.map(_eval_one, param_list, chunksize=1)):
            results.append(res)
            # Progress logging every 1000 tasks
            if (i + 1) % 1000 == 0 or (i + 1) == total_tasks:
                logger.info(
                    "fine search progress",
                    extra={
                        "completed": i + 1,
                        "total": total_tasks,
                        "percent": round((i + 1) / total_tasks * 100, 1),
                    },
                )

    logger.info(
        "stage 2 complete",
        extra={"num_evaluated": len(results)},
    )

    return results


def _generate_neighbor_weights(base_weights, step, top_k=3):
    """주어진 가중치 주변의 이웃 조합 생성 (±step).

    상위 K개 가중치를 가진 전략들만 조정하여 조합 폭발 방지.

    Args:
        base_weights: 기준 가중치 딕셔너리
        step: 조정 단위
        top_k: 조정할 상위 전략 개수 (기본값: 3)

    Returns:
        이웃 가중치 조합 리스트
    """
    neighbors = []

    # 가중치가 큰 상위 K개 전략 선택
    sorted_weights = sorted(base_weights.items(), key=lambda x: x[1], reverse=True)
    top_k_keys = [k for k, v in sorted_weights[:top_k]]

    # 상위 K개 전략들 간에만 조정 시도
    for key_i in top_k_keys:
        for delta_i in [-step, step]:
            new_val_i = base_weights[key_i] + delta_i
            if new_val_i < 0 or new_val_i > 1:
                continue

            # 다른 상위 전략에서 보상
            for key_j in top_k_keys:
                if key_i == key_j:
                    continue

                new_val_j = base_weights[key_j] - delta_i
                if new_val_j < 0 or new_val_j > 1:
                    continue

                # 새로운 가중치 조합 생성
                new_weights = base_weights.copy()
                new_weights[key_i] = new_val_i
                new_weights[key_j] = new_val_j

                # 합이 1.0인지 확인 (부동소수점 오차 허용)
                total = sum(new_weights.values())
                if abs(total - 1.0) < 1e-6:
                    # 반올림하여 정확히 1.0으로 만들기
                    normalized = {k: round(v, 10) for k, v in new_weights.items()}
                    neighbors.append(normalized)

    return neighbors


def _generate_threshold_candidates():
    raw = settings.opt_thresholds.strip()
    if raw:
        return [float(x) for x in raw.split(",") if x.strip()]

    return [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5]


def _generate_weight_grid(step):
    """동적으로 N개 전략에 대한 가중치 그리드 생성 (재귀 방식)."""
    try:
        step = float(step)
    except Exception:
        step = 0.1
    if step <= 0 or step > 1:
        step = 0.1

    units = int(round(1.0 / step))
    num_strategies = len(STRATEGY_KEYS)

    def _generate_combinations(remaining_units, num_remaining):
        """재귀적으로 가중치 조합 생성.

        Args:
            remaining_units: 남은 units 수
            num_remaining: 남은 전략 개수

        Returns:
            가능한 모든 조합 리스트 (각 조합은 리스트)
        """
        if num_remaining == 1:
            # 마지막 전략: 남은 units를 모두 할당
            return [[remaining_units]]

        combinations = []
        for i in range(remaining_units + 1):
            # 현재 전략에 i units 할당
            # 나머지 전략들에 대해 재귀 호출
            sub_combinations = _generate_combinations(remaining_units - i, num_remaining - 1)
            for sub_comb in sub_combinations:
                combinations.append([i] + sub_comb)

        return combinations

    # 모든 조합 생성
    raw_combinations = _generate_combinations(units, num_strategies)

    # 딕셔너리 형태로 변환
    candidates = []
    for combo in raw_combinations:
        weights_list = [float(x) / float(units) for x in combo]
        weights_dict = {k: v for k, v in zip(STRATEGY_KEYS, weights_list)}
        candidates.append(weights_dict)

    return candidates


def _backtest(
    candles,
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

    window = max(3, min(int(window), len(candles)))

    # Early stopping 설정
    early_stop_threshold = settings.opt_early_stop_threshold
    early_stop_candles = settings.opt_early_stop_candles

    # i는 "시그널을 계산하는 시점" (Close 기준)
    # 거래는 i+1 시점의 Open 가격으로 체결
    for i in range(len(candles) - 1):
        # 다음 시점(i+1)의 시가로 거래 체결
        next_open = candles[i + 1]["open"]
        next_close = candles[i + 1]["close"]  # 평가금액 계산용

        # 매 시점의 평가금액 기록 (다음 봉 종가 기준)
        equity = cash_krw + coin_qty * next_close
        equity_curve.append(equity)

        if i > 0 and last_equity > 0:
            returns.append((equity - last_equity) / last_equity)

        last_equity = equity

        # 초반 캔들에서 손실이 임계값 이하면 중단
        if i >= early_stop_candles:
            current_return = (equity / float(initial_cash)) - 1.0
            if current_return <= early_stop_threshold:
                return {
                    "final_equity": equity,
                    "total_return": current_return,
                    "max_drawdown": 1.0,
                    "sharpe": -999.0,
                    "win_rate": 0.0,
                    "num_trades": total_trades,
                }

        # 전략 계산에 필요한 최소 캔들 수 확보 후 진행
        if i + 1 < max(3, window):
            continue

        # 최근 window개의 캔들(종가)로 시그널 계산 (현재 시점 i 포함)
        # candles[i]까지의 데이터만 사용해야 함 (미래 참조 방지)
        recent_closes = [c["close"] for c in candles[i + 1 - window : i + 1]]
        score = float(ensemble_signal(recent_closes, weights))

        # 거래 체결 가격은 다음 봉 시가
        exec_price = next_open

        # BUY
        if score >= threshold:
            if cash_krw > min_order_krw:
                target_price = round_price_to_tick(exec_price * (1.0 + aggressiveness), mode="up")
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
                    exec_price * (1.0 - aggressiveness), mode="down"
                )
                proceed = target_price * coin_qty
                if proceed > min_order_krw:
                    fee = proceed * fee_rate
                    cash_krw += proceed - fee

                    after_equity = cash_krw
                    if after_equity > equity:
                        win_trades += 1

                    coin_qty = 0.0
                    total_trades += 1

    final_equity = cash_krw + coin_qty * candles[-1]["close"]

    total_return = (final_equity / float(initial_cash)) - 1.0
    max_dd = _max_drawdown(equity_curve)
    sharpe = _sharpe_ratio(returns)
    win_rate = (win_trades / total_trades) if total_trades > 0 else 0.0

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
