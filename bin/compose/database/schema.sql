-- TimescaleDB schema (single-symbol Upbit setup)

-- Extensions
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Candles (hypertable)
CREATE TABLE IF NOT EXISTS candles (
  timeframe TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  open NUMERIC(18,8) NOT NULL,
  high NUMERIC(18,8) NOT NULL,
  low NUMERIC(18,8) NOT NULL,
  close NUMERIC(18,8) NOT NULL,
  volume NUMERIC(28,8) NOT NULL,
  quote_volume NUMERIC(28,8),
  meta JSONB DEFAULT '{}',
  PRIMARY KEY (timeframe, ts)
);
SELECT create_hypertable('candles', 'ts', if_not_exists => TRUE, migrate_data => TRUE, chunk_time_interval => interval '7 days');
CREATE INDEX IF NOT EXISTS idx_candles_tf_ts ON candles (timeframe, ts DESC);

-- Orders
CREATE TABLE IF NOT EXISTS orders (
  id BIGSERIAL PRIMARY KEY,
  client_order_id UUID DEFAULT gen_random_uuid(),
  side TEXT NOT NULL CHECK (side IN ('buy','sell')),
  order_type TEXT NOT NULL CHECK (order_type IN ('market','limit')),
  price NUMERIC(18,8),
  quantity NUMERIC(28,8) NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('new','partially_filled','filled','canceled','rejected')),
  placed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  exchange_order_id TEXT,
  meta JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_orders_status_time ON orders (status, placed_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_client_id ON orders (client_order_id);

-- Trades (hypertable)
CREATE TABLE IF NOT EXISTS trades (
  id BIGSERIAL,
  order_id BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  executed_at TIMESTAMPTZ NOT NULL,
  price NUMERIC(18,8) NOT NULL,
  quantity NUMERIC(28,8) NOT NULL,
  fee NUMERIC(18,8) DEFAULT 0,
  fee_asset TEXT,
  slippage NUMERIC(10,8),
  meta JSONB DEFAULT '{}',
  PRIMARY KEY (id, executed_at)
);
SELECT create_hypertable('trades', 'executed_at', if_not_exists => TRUE, chunk_time_interval => interval '30 days');
CREATE INDEX IF NOT EXISTS idx_trades_order_time ON trades (order_id, executed_at DESC);

-- Positions
CREATE TABLE IF NOT EXISTS positions (
  id BIGSERIAL PRIMARY KEY,
  strategy_name TEXT NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('long','short')),
  quantity NUMERIC(28,8) NOT NULL,
  avg_price NUMERIC(18,8) NOT NULL,
  opened_at TIMESTAMPTZ NOT NULL,
  closed_at TIMESTAMPTZ,
  status TEXT NOT NULL CHECK (status IN ('open','closed')) DEFAULT 'open',
  realized_pnl NUMERIC(18,8) DEFAULT 0,
  unrealized_pnl NUMERIC(18,8),
  meta JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_positions_strategy_status ON positions (strategy_name, status);

-- Equity curve (hypertable)
CREATE TABLE IF NOT EXISTS equity_curve (
  strategy_name TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  equity NUMERIC(28,8) NOT NULL,
  cash NUMERIC(28,8),
  pnl NUMERIC(28,8),
  meta JSONB DEFAULT '{}',
  PRIMARY KEY (strategy_name, ts)
);
SELECT create_hypertable('equity_curve', 'ts', if_not_exists => TRUE, chunk_time_interval => interval '7 days');

-- Optimizer results
CREATE TABLE IF NOT EXISTS optimizer_results (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  params JSONB NOT NULL,
  metrics JSONB NOT NULL,
  is_best BOOLEAN DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_optimizer_results_time ON optimizer_results (created_at DESC);

