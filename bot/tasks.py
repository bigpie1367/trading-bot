from celery import Celery, chain, chord

from bot import collector, optimizer, trader
from bot.core.config import settings

app = Celery(
    "trading_bot",
    broker=settings.celery_broker_url,
    backend=settings.celery_backend_url,
)

app.conf.broker_connection_retry_on_startup = True


@app.task(queue="collector_queue")
def collect_data():
    collector.run()


@app.task(queue="trader_queue")
def run_trade():
    trader.run()


@app.task(queue="optimizer_queue")
def start_optimization():
    """최적화 시작: 파라미터 생성 및 1단계 Coarse Search 실행 (Chord)."""
    from bot.core.config import settings
    from bot.db.storage import load_ohlcv

    # 데이터 로드
    candles = load_ohlcv(timeframe="1m", months=3)
    if len(candles) < 200:
        return

    # 1단계 파라미터 생성
    params = optimizer.generate_coarse_params()

    # 공통 설정
    initial_cash = settings.opt_initial_cash
    fee_rate = settings.fee_rate
    fee_buffer = settings.fee_buffer
    aggressiveness = settings.aggressiveness
    window = settings.opt_window

    # Chord 실행: [Backtests...] -> on_coarse_complete
    header = [
        run_single_backtest.s(
            candles,
            p["weights"],
            p["threshold"],
            initial_cash,
            fee_rate,
            fee_buffer,
            aggressiveness,
            window,
        )
        for p in params
    ]

    # 콜백에 candles 등 필요한 데이터 전달
    callback = on_coarse_complete.s(
        candles=candles,
        initial_cash=initial_cash,
        fee_rate=fee_rate,
        fee_buffer=fee_buffer,
        aggressiveness=aggressiveness,
        window=window,
    )

    chain(chord(header)(callback)).delay()


@app.task(queue="optimizer_queue")
def on_coarse_complete(
    results, candles, initial_cash, fee_rate, fee_buffer, aggressiveness, window
):
    """1단계 완료 후 호출: 결과 분석 및 2단계 Fine Search 실행 (Chord)."""

    # 2단계 파라미터 생성
    fine_params = optimizer.generate_fine_params(results)

    # Chord 실행: [Backtests...] -> on_fine_complete
    header = [
        run_single_backtest.s(
            candles,
            p["weights"],
            p["threshold"],
            initial_cash,
            fee_rate,
            fee_buffer,
            aggressiveness,
            window,
        )
        for p in fine_params
    ]

    # 콜백에 1단계 결과도 전달 (최종 병합용)
    callback = on_fine_complete.s(coarse_results=results)

    chain(chord(header)(callback)).delay()


@app.task(queue="optimizer_queue")
def on_fine_complete(fine_results, coarse_results):
    """2단계 완료 후 호출: 최종 결과 병합 및 저장."""
    all_results = coarse_results + fine_results
    optimizer.save_best_result(all_results)


@app.task(queue="optimizer_queue")
def run_single_backtest(
    candles, weights, threshold, initial_cash, fee_rate, fee_buffer, aggressiveness, window
):
    from bot.optimizer import run_backtest

    metrics = run_backtest(
        candles, weights, threshold, initial_cash, fee_rate, fee_buffer, aggressiveness, window
    )

    return (metrics, {"weights": weights, "threshold": threshold})


# ------------------------------
# Coordinator: collect -> trade
# ------------------------------


@app.task(queue="collector_queue")
def collect_and_trade():
    chain(
        collect_data.si().set(queue="collector_queue"),
        run_trade.si().set(queue="trader_queue"),
    ).delay()
