-- PureGamma strategy control plane. Runtime execution remains isolated.
CREATE TABLE trading_accounts (
  id VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name VARCHAR NOT NULL, venue VARCHAR NOT NULL, account_type VARCHAR NOT NULL, base_currency VARCHAR NOT NULL,
  status VARCHAR NOT NULL, permissions_json JSON NOT NULL, error_code VARCHAR, error_message TEXT,
  created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
);
CREATE TABLE exchange_connections (
  id VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  account_id VARCHAR NOT NULL REFERENCES trading_accounts(id) ON DELETE CASCADE, adapter VARCHAR NOT NULL,
  environment VARCHAR NOT NULL, credential_reference VARCHAR, status VARCHAR NOT NULL,
  last_health_at TIMESTAMP, metadata_json JSON NOT NULL, error_code VARCHAR, error_message TEXT,
  created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL,
  CONSTRAINT uq_exchange_connection_account_adapter UNIQUE(user_id, account_id, adapter)
);
CREATE TABLE strategies (
  id VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  conversation_id VARCHAR REFERENCES agent_conversations(id) ON DELETE SET NULL, name VARCHAR NOT NULL,
  description TEXT NOT NULL, status VARCHAR NOT NULL, current_version INTEGER NOT NULL,
  execution_mode VARCHAR NOT NULL, error_code VARCHAR, error_message TEXT,
  created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
);
CREATE TABLE strategy_versions (
  id VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  strategy_id VARCHAR NOT NULL REFERENCES strategies(id) ON DELETE CASCADE, version INTEGER NOT NULL,
  draft_json JSON NOT NULL, config_hash VARCHAR NOT NULL, status VARCHAR NOT NULL,
  created_by VARCHAR NOT NULL, created_at TIMESTAMP NOT NULL,
  CONSTRAINT uq_strategy_version UNIQUE(strategy_id, version)
);
CREATE TABLE strategy_intents (
  id VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  conversation_id VARCHAR REFERENCES agent_conversations(id) ON DELETE SET NULL,
  strategy_id VARCHAR NOT NULL REFERENCES strategies(id) ON DELETE CASCADE, strategy_version INTEGER NOT NULL,
  intent_type VARCHAR NOT NULL, execution_mode VARCHAR NOT NULL, payload_json JSON NOT NULL,
  config_hash VARCHAR NOT NULL, idempotency_key VARCHAR NOT NULL UNIQUE, confirmation_required BOOLEAN NOT NULL,
  confirmation_token_hash VARCHAR, approval_status VARCHAR NOT NULL, status VARCHAR NOT NULL,
  expires_at TIMESTAMP NOT NULL, approved_at TIMESTAMP, error_code VARCHAR, error_message TEXT,
  created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
);
CREATE TABLE strategy_activations (
  id VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  conversation_id VARCHAR REFERENCES agent_conversations(id) ON DELETE SET NULL,
  strategy_id VARCHAR NOT NULL REFERENCES strategies(id) ON DELETE CASCADE, strategy_version INTEGER NOT NULL,
  intent_id VARCHAR NOT NULL UNIQUE REFERENCES strategy_intents(id) ON DELETE CASCADE,
  execution_mode VARCHAR NOT NULL, status VARCHAR NOT NULL, runtime_command_id VARCHAR,
  runtime_ack_json JSON NOT NULL, activated_at TIMESTAMP, stopped_at TIMESTAMP,
  error_code VARCHAR, error_message TEXT, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
);
CREATE TABLE strategy_risk_policies (
  id VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  strategy_id VARCHAR NOT NULL REFERENCES strategies(id) ON DELETE CASCADE, strategy_version INTEGER NOT NULL,
  max_position FLOAT NOT NULL, max_notional FLOAT NOT NULL, max_leverage FLOAT NOT NULL,
  max_daily_loss FLOAT NOT NULL, max_drawdown FLOAT NOT NULL, max_orders_per_minute INTEGER NOT NULL,
  reduce_only BOOLEAN NOT NULL, pause_opening BOOLEAN NOT NULL, global_kill_switch BOOLEAN NOT NULL,
  policy_json JSON NOT NULL, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL,
  CONSTRAINT uq_strategy_risk_version UNIQUE(strategy_id, strategy_version)
);
CREATE TABLE strategy_runs (
  id VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  strategy_id VARCHAR NOT NULL REFERENCES strategies(id) ON DELETE CASCADE, strategy_version INTEGER NOT NULL,
  account_id VARCHAR REFERENCES trading_accounts(id) ON DELETE SET NULL,
  activation_id VARCHAR REFERENCES strategy_activations(id) ON DELETE SET NULL,
  runtime_run_id VARCHAR NOT NULL UNIQUE, execution_mode VARCHAR NOT NULL, status VARCHAR NOT NULL,
  started_at TIMESTAMP, stopped_at TIMESTAMP, performance_json JSON NOT NULL,
  error_code VARCHAR, error_message TEXT, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
);
CREATE TABLE signal_events (
  id VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  strategy_id VARCHAR NOT NULL REFERENCES strategies(id) ON DELETE CASCADE, strategy_version INTEGER NOT NULL,
  run_id VARCHAR NOT NULL REFERENCES strategy_runs(id) ON DELETE CASCADE, source_ids JSON NOT NULL,
  source_urls JSON NOT NULL, data_timestamp TIMESTAMP NOT NULL, fetch_timestamp TIMESTAMP NOT NULL,
  freshness FLOAT NOT NULL, credibility_score FLOAT NOT NULL, sentiment_score FLOAT NOT NULL,
  confidence FLOAT NOT NULL, asset VARCHAR NOT NULL, model_version VARCHAR NOT NULL,
  feature_version VARCHAR NOT NULL, signal_direction VARCHAR NOT NULL, signal_strength FLOAT NOT NULL,
  target_position FLOAT NOT NULL, execution_note TEXT, risk_state VARCHAR NOT NULL,
  raw_event_reference JSON NOT NULL, idempotency_key VARCHAR NOT NULL UNIQUE, created_at TIMESTAMP NOT NULL
);
CREATE TABLE order_intents (
  id VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  conversation_id VARCHAR REFERENCES agent_conversations(id) ON DELETE SET NULL,
  strategy_id VARCHAR REFERENCES strategies(id) ON DELETE SET NULL, strategy_version INTEGER,
  run_id VARCHAR REFERENCES strategy_runs(id) ON DELETE SET NULL,
  account_id VARCHAR NOT NULL REFERENCES trading_accounts(id) ON DELETE CASCADE,
  instrument VARCHAR NOT NULL, venue VARCHAR NOT NULL, direction VARCHAR NOT NULL,
  quantity FLOAT NOT NULL, notional FLOAT NOT NULL, leverage FLOAT NOT NULL, order_type VARCHAR NOT NULL,
  reduce_only BOOLEAN NOT NULL, execution_mode VARCHAR NOT NULL, status VARCHAR NOT NULL,
  risk_limits_json JSON NOT NULL, idempotency_key VARCHAR NOT NULL UNIQUE,
  confirmation_token_hash VARCHAR, approval_status VARCHAR NOT NULL, expires_at TIMESTAMP NOT NULL,
  raw_event_reference JSON NOT NULL, error_code VARCHAR, error_message TEXT,
  created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
);
CREATE TABLE risk_decisions (
  id VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  strategy_id VARCHAR REFERENCES strategies(id) ON DELETE SET NULL,
  run_id VARCHAR REFERENCES strategy_runs(id) ON DELETE SET NULL,
  order_intent_id VARCHAR NOT NULL REFERENCES order_intents(id) ON DELETE CASCADE,
  decision VARCHAR NOT NULL, reasons JSON NOT NULL, limits_json JSON NOT NULL,
  state_json JSON NOT NULL, created_at TIMESTAMP NOT NULL
);
CREATE TABLE order_journal (
  id VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  account_id VARCHAR NOT NULL REFERENCES trading_accounts(id) ON DELETE CASCADE,
  strategy_id VARCHAR REFERENCES strategies(id) ON DELETE SET NULL,
  run_id VARCHAR REFERENCES strategy_runs(id) ON DELETE SET NULL,
  order_intent_id VARCHAR NOT NULL REFERENCES order_intents(id) ON DELETE CASCADE,
  client_order_id VARCHAR NOT NULL, exchange_order_id VARCHAR, sequence INTEGER NOT NULL, state VARCHAR NOT NULL,
  instrument VARCHAR NOT NULL, side VARCHAR NOT NULL, quantity FLOAT NOT NULL, filled_quantity FLOAT NOT NULL,
  remaining_quantity FLOAT NOT NULL, average_price FLOAT, reduce_only BOOLEAN NOT NULL,
  event_json JSON NOT NULL, raw_event_reference JSON NOT NULL, idempotency_key VARCHAR NOT NULL UNIQUE,
  error_code VARCHAR, error_message TEXT, created_at TIMESTAMP NOT NULL,
  CONSTRAINT uq_order_journal_sequence UNIQUE(client_order_id, sequence)
);
CREATE TABLE position_snapshots (
  id VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  account_id VARCHAR NOT NULL REFERENCES trading_accounts(id) ON DELETE CASCADE,
  strategy_id VARCHAR REFERENCES strategies(id) ON DELETE SET NULL,
  run_id VARCHAR REFERENCES strategy_runs(id) ON DELETE SET NULL, instrument VARCHAR NOT NULL,
  quantity FLOAT NOT NULL, side VARCHAR NOT NULL, average_price FLOAT NOT NULL, mark_price FLOAT NOT NULL,
  unrealized_pnl FLOAT NOT NULL, realized_pnl FLOAT NOT NULL, leverage FLOAT NOT NULL,
  raw_event_reference JSON NOT NULL, captured_at TIMESTAMP NOT NULL
);
CREATE TABLE account_snapshots (
  id VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  account_id VARCHAR NOT NULL REFERENCES trading_accounts(id) ON DELETE CASCADE,
  balance FLOAT NOT NULL, equity FLOAT NOT NULL, available_margin FLOAT NOT NULL,
  daily_pnl FLOAT NOT NULL, drawdown FLOAT NOT NULL, exposure FLOAT NOT NULL, stale BOOLEAN NOT NULL,
  raw_event_reference JSON NOT NULL, captured_at TIMESTAMP NOT NULL
);
CREATE TABLE reconciliation_records (
  id VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  account_id VARCHAR NOT NULL REFERENCES trading_accounts(id) ON DELETE CASCADE,
  strategy_id VARCHAR REFERENCES strategies(id) ON DELETE SET NULL,
  run_id VARCHAR REFERENCES strategy_runs(id) ON DELETE SET NULL, status VARCHAR NOT NULL,
  local_state_json JSON NOT NULL, exchange_state_json JSON NOT NULL, differences_json JSON NOT NULL,
  actions_json JSON NOT NULL, raw_event_reference JSON NOT NULL, error_code VARCHAR, error_message TEXT,
  completed_at TIMESTAMP, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
);
CREATE TABLE trading_audit_logs (
  id VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  conversation_id VARCHAR REFERENCES agent_conversations(id) ON DELETE SET NULL,
  strategy_id VARCHAR REFERENCES strategies(id) ON DELETE SET NULL,
  run_id VARCHAR REFERENCES strategy_runs(id) ON DELETE SET NULL, action VARCHAR NOT NULL,
  status VARCHAR NOT NULL, actor_type VARCHAR NOT NULL, request_json JSON NOT NULL, result_json JSON NOT NULL,
  idempotency_key VARCHAR NOT NULL UNIQUE, error_code VARCHAR, error_message TEXT, created_at TIMESTAMP NOT NULL
);
