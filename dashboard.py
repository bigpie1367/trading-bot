import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from bot.core.config import settings
from bot.core.context import get_db_connection
from bot.exchange.upbit import fetch_account_balances
from plotly.subplots import make_subplots

st.set_page_config(layout="wide", page_title="Trading Bot Dashboard")
st.title("🤖 Trading Bot Dashboard")

# ---------------------------
# Sidebar & Configuration
# ---------------------------
st.sidebar.header("Configuration")

# DB Connection for initial setup
try:
    conn = get_db_connection()
except Exception as e:
    st.error(f"Failed to connect to DB: {e}")
    st.stop()


@st.cache_data(ttl=60)
def load_market_options():
    with get_db_connection() as conn:
        # Get available markets from candles
        query = "SELECT DISTINCT meta->>'market' as market FROM candles WHERE meta->>'market' IS NOT NULL"
        df = pd.read_sql(query, conn)
        if df.empty:
            return ["KRW-BTC"]  # Default
        return df["market"].tolist()


markets = load_market_options()
selected_market = st.sidebar.selectbox("Select Market", markets, index=0)

timeframe = st.sidebar.selectbox(
    "Timeframe", ["1m", "3m", "5m", "15m", "30m", "60m", "240m", "1d"], index=0
)
days_to_load = st.sidebar.slider("Days to Load", min_value=1, max_value=7, value=3)


# ---------------------------
# Data Loading
# ---------------------------
@st.cache_data(ttl=10)
def load_data(market, timeframe, days):
    with get_db_connection() as conn:
        # Load Candles - using parameterized query to prevent SQL injection
        candles_query = """
            SELECT ts, open, high, low, close, volume
            FROM candles
            WHERE timeframe = %(timeframe)s
              AND meta->>'market' = %(market)s
              AND ts >= NOW() - INTERVAL '1 day' * %(days)s
            ORDER BY ts ASC
        """
        df_candles = pd.read_sql(
            candles_query, conn, params={"timeframe": timeframe, "market": market, "days": days}
        )

        if not df_candles.empty:
            df_candles["ts"] = pd.to_datetime(df_candles["ts"])
            df_candles.set_index("ts", inplace=True)

        # Load Trades - using parameterized query to prevent SQL injection
        trades_query = """
            SELECT
                t.executed_at,
                t.price,
                t.quantity,
                o.side,
                t.fee,
                (t.price * t.quantity) as trade_amount
            FROM trades t
            JOIN orders o ON t.order_id = o.id
            WHERE t.executed_at >= NOW() - INTERVAL '1 day' * %(days)s
              AND o.meta->>'market' = %(market)s
            ORDER BY t.executed_at ASC
        """
        df_trades = pd.read_sql(trades_query, conn, params={"market": market, "days": days})
        if not df_trades.empty:
            df_trades["executed_at"] = pd.to_datetime(df_trades["executed_at"])

            # Calculate profit/loss using weighted average cost basis
            df_trades["pnl"] = 0.0
            accumulated_cost = 0.0
            accumulated_qty = 0.0

            for idx in df_trades.index:
                if df_trades.loc[idx, "side"] == "buy":
                    buy_cost = df_trades.loc[idx, "trade_amount"] + df_trades.loc[idx, "fee"]
                    buy_qty = df_trades.loc[idx, "quantity"]
                    accumulated_cost += buy_cost
                    accumulated_qty += buy_qty
                    df_trades.loc[idx, "pnl"] = 0.0  # No P&L on buy
                elif df_trades.loc[idx, "side"] == "sell" and accumulated_qty > 0:
                    sell_qty = df_trades.loc[idx, "quantity"]
                    avg_cost_per_unit = accumulated_cost / accumulated_qty
                    cost_basis = avg_cost_per_unit * sell_qty
                    sell_amount = df_trades.loc[idx, "trade_amount"] - df_trades.loc[idx, "fee"]
                    df_trades.loc[idx, "pnl"] = sell_amount - cost_basis
                    accumulated_cost -= cost_basis
                    accumulated_qty -= sell_qty

    return df_candles, df_trades


@st.cache_data(ttl=60)
def load_optimizer_results():
    """Load latest optimizer results from database."""
    with get_db_connection() as conn:
        query = """
            SELECT
                created_at,
                params,
                metrics,
                is_best
            FROM optimizer_results
            ORDER BY created_at DESC
            LIMIT 1
        """
        df = pd.read_sql(query, conn)
        if df.empty:
            return None
        return df.iloc[0]


with st.spinner("Loading data..."):
    df_candles, df_trades = load_data(selected_market, timeframe, days_to_load)
    optimizer_result = load_optimizer_results()

if df_candles.empty:
    st.warning("No candle data found for the selected criteria.")
    st.stop()

# ---------------------------
# Metrics
# ---------------------------
col1, col2, col3, col4 = st.columns(4)

current_price = df_candles.iloc[-1]["close"]
start_price = df_candles.iloc[0]["close"]
period_return = ((current_price - start_price) / start_price) * 100

with col1:
    st.metric("Current Price", f"{current_price:,.0f}", f"{period_return:.2f}%")

total_trades = len(df_trades)
buy_trades = df_trades[df_trades["side"] == "buy"]
sell_trades = df_trades[df_trades["side"] == "sell"]

with col2:
    st.metric("Total Trades", total_trades)

# Calculate Total Balance from Upbit Account (KRW + Crypto Holdings)
try:
    account_balances = fetch_account_balances()

    krw_balance = 0.0
    crypto_value_krw = 0.0

    # Calculate KRW balance and crypto holdings value
    for balance in account_balances:
        currency = balance.get("currency")
        balance_amount = float(balance.get("balance", 0))

        if currency == "KRW":
            krw_balance = balance_amount
        else:
            # For crypto holdings, calculate KRW value using current price
            avg_buy_price = float(balance.get("avg_buy_price", 0))
            if avg_buy_price > 0 and balance_amount > 0:
                # Use current market price from candles if available for this market
                market_code = f"KRW-{currency}"
                if market_code == selected_market and not df_candles.empty:
                    current_crypto_price = df_candles.iloc[-1]["close"]
                    crypto_value_krw += balance_amount * current_crypto_price
                else:
                    # Fallback to avg_buy_price if we don't have current price
                    crypto_value_krw += balance_amount * avg_buy_price

    # Total balance = KRW + Crypto holdings in KRW
    total_balance = krw_balance + crypto_value_krw

    # Calculate balance change from trades
    if not df_trades.empty:
        total_pnl = df_trades["pnl"].sum()
        # Estimate initial balance by subtracting total PnL from current balance
        estimated_initial = total_balance - total_pnl
        if estimated_initial > 0:
            pnl_percent = (total_pnl / estimated_initial) * 100
        else:
            pnl_percent = 0
        with col3:
            st.metric("Total Balance", f"{total_balance:,.0f} KRW", f"{pnl_percent:+.2f}%")
            # Show breakdown in smaller text
            st.caption(f"💵 Cash: {krw_balance:,.0f} KRW | 🪙 Crypto: {crypto_value_krw:,.0f} KRW")
    else:
        with col3:
            st.metric("Total Balance", f"{total_balance:,.0f} KRW", "0.00%")
            st.caption(f"💵 Cash: {krw_balance:,.0f} KRW | 🪙 Crypto: {crypto_value_krw:,.0f} KRW")
except Exception as e:
    st.warning(f"Failed to fetch Upbit balance: {e}")
    initial_cash = settings.opt_initial_cash
    if not df_trades.empty:
        total_pnl = df_trades["pnl"].sum()
        current_balance = initial_cash + total_pnl
        pnl_percent = (total_pnl / initial_cash) * 100 if initial_cash > 0 else 0
        with col3:
            st.metric("Total Balance", f"{current_balance:,.0f} KRW", f"{pnl_percent:+.2f}%")
    else:
        with col3:
            st.metric("Total Balance", f"{initial_cash:,.0f} KRW", "0.00%")

# Win Rate Calculation
if not sell_trades.empty and not buy_trades.empty:
    # Simple approximation: compare sell price with average buy price
    avg_buy_price = buy_trades["price"].mean()
    winning_sells = sell_trades[sell_trades["price"] > avg_buy_price]
    win_rate = (len(winning_sells) / len(sell_trades)) * 100 if len(sell_trades) > 0 else 0
    with col4:
        st.metric("Win Rate", f"{win_rate:.1f}%")
else:
    with col4:
        st.metric("Win Rate", "N/A")

# ---------------------------
# Optimizer Metrics Section
# ---------------------------
st.subheader("📊 Current Optimization Metrics")

if optimizer_result is not None:
    opt_col1, opt_col2, opt_col3, opt_col4, opt_col5 = st.columns(5)

    metrics = optimizer_result["metrics"]
    params = optimizer_result["params"]

    with opt_col1:
        st.metric(
            "Total Return",
            f"{metrics.get('total_return', 0) * 100:.2f}%",
            help="Backtest total return",
        )

    with opt_col2:
        st.metric(
            "Sharpe Ratio", f"{metrics.get('sharpe', 0):.2f}", help="Risk-adjusted return metric"
        )

    with opt_col3:
        st.metric(
            "Max Drawdown",
            f"{metrics.get('max_drawdown', 0) * 100:.2f}%",
            help="Maximum peak-to-trough decline",
        )

    with opt_col4:
        st.metric(
            "Backtest Win Rate",
            f"{metrics.get('win_rate', 0) * 100:.1f}%",
            help="Percentage of profitable trades in backtest",
        )

    with opt_col5:
        st.metric(
            "Backtest Trades",
            f"{metrics.get('num_trades', 0)}",
            help="Number of trades in backtest",
        )

    # Optimizer Parameters
    with st.expander("🔧 Optimizer Parameters", expanded=False):
        param_col1, param_col2 = st.columns(2)

        with param_col1:
            st.write("**Threshold:**", f"{params.get('threshold', 0):.2f}")
            st.write("**Last Updated:**", optimizer_result["created_at"])

        with param_col2:
            st.write("**Strategy Weights:**")
            weights = params.get("weights", {})
            # Sort by weight descending
            sorted_weights = sorted(weights.items(), key=lambda x: x[1], reverse=True)
            for strategy, weight in sorted_weights:
                if weight > 0:  # Only show non-zero weights
                    st.write(f"- {strategy}: {weight:.2f}")
else:
    st.info("No optimization results found. Run the optimizer to see metrics.")

# ---------------------------
# Trade Statistics
# ---------------------------
if not df_trades.empty:
    st.subheader("💰 Trade Statistics")

    stat_col1, stat_col2, stat_col3 = st.columns(3)

    with stat_col1:
        st.write("**Buy Trades:**", len(buy_trades))
        if not buy_trades.empty:
            st.write("**Avg Buy Price:**", f"{buy_trades['price'].mean():,.0f} KRW")
            st.write(
                "**Total Buy Volume:**",
                f"{(buy_trades['quantity'] * buy_trades['price']).sum():,.0f} KRW",
            )

    with stat_col2:
        st.write("**Sell Trades:**", len(sell_trades))
        if not sell_trades.empty:
            st.write("**Avg Sell Price:**", f"{sell_trades['price'].mean():,.0f} KRW")
            st.write(
                "**Total Sell Volume:**",
                f"{(sell_trades['quantity'] * sell_trades['price']).sum():,.0f} KRW",
            )

    with stat_col3:
        total_fees = df_trades["fee"].sum()
        st.write("**Total Fees:**", f"{total_fees:,.0f} KRW")
        if not buy_trades.empty and not sell_trades.empty:
            # Rough PnL estimation
            total_buy = (buy_trades["quantity"] * buy_trades["price"]).sum()
            total_sell = (sell_trades["quantity"] * sell_trades["price"]).sum()
            estimated_pnl = total_sell - total_buy - total_fees
            st.write("**Est. PnL:**", f"{estimated_pnl:,.0f} KRW")
            if total_buy > 0:
                pnl_pct = (estimated_pnl / total_buy) * 100
                st.write("**Est. PnL %:**", f"{pnl_pct:.2f}%")


# ---------------------------
# Charts
# ---------------------------
st.subheader("Price & Trades")

fig = make_subplots(
    rows=2,
    cols=1,
    shared_xaxes=True,
    vertical_spacing=0.05,
    subplot_titles=("Price", "Volume"),
    row_heights=[0.8, 0.2],  # Give more space to price chart
)

# Candlestick
fig.add_trace(
    go.Candlestick(
        x=df_candles.index,
        open=df_candles["open"],
        high=df_candles["high"],
        low=df_candles["low"],
        close=df_candles["close"],
        name="OHLC",
    ),
    row=1,
    col=1,
)

# Trades
if not df_trades.empty:
    # Buys
    buys = df_trades[df_trades["side"] == "buy"]
    if not buys.empty:
        fig.add_trace(
            go.Scatter(
                x=buys["executed_at"],
                y=buys["price"],
                mode="markers",
                marker=dict(
                    symbol="triangle-up",
                    size=12,
                    color="green",
                    line=dict(width=1, color="darkgreen"),
                ),
                name="Buy",
            ),
            row=1,
            col=1,
        )

    # Sells
    sells = df_trades[df_trades["side"] == "sell"]
    if not sells.empty:
        fig.add_trace(
            go.Scatter(
                x=sells["executed_at"],
                y=sells["price"],
                mode="markers",
                marker=dict(
                    symbol="triangle-down",
                    size=12,
                    color="red",
                    line=dict(width=1, color="darkred"),
                ),
                name="Sell",
            ),
            row=1,
            col=1,
        )

# Volume
fig.add_trace(
    go.Bar(
        x=df_candles.index,
        y=df_candles["volume"],
        name="Volume",
        marker_color="rgba(100, 150, 200, 0.5)",
    ),
    row=2,
    col=1,
)

fig.update_layout(
    height=1000,
    xaxis_rangeslider_visible=False,
    hovermode="x unified",
    showlegend=True,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)

# Set initial x-axis range to show last 3 days for better candle visibility
if len(df_candles) > 0:
    last_timestamp = df_candles.index[-1]
    first_visible = last_timestamp - pd.Timedelta(days=3)
    fig.update_xaxes(range=[first_visible, last_timestamp])

# Update y-axis labels
fig.update_yaxes(title_text="Price (KRW)", row=1, col=1)
fig.update_yaxes(title_text="Volume", row=2, col=1)

st.plotly_chart(fig, use_container_width=True)

# ---------------------------
# Recent Trades Table
# ---------------------------
trades_col1, trades_col2 = st.columns([0.95, 0.05])
with trades_col1:
    st.subheader("Recent Trades")
with trades_col2:
    st.write("")  # Spacer for alignment
    if st.button("🔄", key="refresh_trades"):
        st.cache_data.clear()
        st.rerun()

if not df_trades.empty:
    # Prepare display dataframe
    display_df = df_trades.sort_values("executed_at", ascending=False).copy()
    display_df["executed_at"] = display_df["executed_at"].dt.strftime("%Y-%m-%d %H:%M:%S")

    # Format numeric columns as strings to avoid format errors
    display_df["price_formatted"] = display_df["price"].apply(lambda x: f"{x:,.0f}")
    display_df["quantity_formatted"] = display_df["quantity"].apply(lambda x: f"{x:.8f}")
    display_df["fee_formatted"] = display_df["fee"].apply(lambda x: f"{x:.2f}")
    display_df["amount_formatted"] = display_df["trade_amount"].apply(lambda x: f"{x:,.0f}")
    display_df["pnl_formatted"] = display_df["pnl"].apply(
        lambda x: f"{x:+,.0f}" if x != 0 else "-"
    )

    # Select and reorder columns for display
    display_columns = [
        "executed_at",
        "side",
        "price_formatted",
        "quantity_formatted",
        "amount_formatted",
        "fee_formatted",
        "pnl_formatted",
    ]
    display_df_final = display_df[display_columns]

    st.dataframe(
        display_df_final,
        use_container_width=True,
        column_config={
            "executed_at": st.column_config.TextColumn("Executed At", width="medium"),
            "side": st.column_config.TextColumn("Side", width="small"),
            "price_formatted": st.column_config.TextColumn("Price (KRW)", width="small"),
            "quantity_formatted": st.column_config.TextColumn("Quantity", width="medium"),
            "amount_formatted": st.column_config.TextColumn("Amount (KRW)", width="medium"),
            "fee_formatted": st.column_config.TextColumn("Fee (KRW)", width="small"),
            "pnl_formatted": st.column_config.TextColumn("P&L (KRW)", width="medium"),
        },
        hide_index=True,
    )
else:
    st.info("No trades found in this period.")
