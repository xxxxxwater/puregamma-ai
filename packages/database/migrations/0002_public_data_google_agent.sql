-- PureGamma public data, Google identity, and Agent chat schema.
-- New installations are also supported by SQLAlchemy Base.metadata.create_all.
ALTER TABLE users ADD COLUMN email_verified_at TIMESTAMP NULL;
ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP NULL;
ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0;

CREATE TABLE user_identities (
  id VARCHAR PRIMARY KEY,
  user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider VARCHAR NOT NULL,
  provider_subject VARCHAR NOT NULL,
  provider_email VARCHAR,
  provider_email_verified BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  CONSTRAINT uq_identity_provider_subject UNIQUE (provider, provider_subject)
);
CREATE INDEX ix_user_identities_user_id ON user_identities(user_id);

CREATE TABLE data_sources (
  id VARCHAR PRIMARY KEY,
  name VARCHAR NOT NULL,
  category VARCHAR NOT NULL,
  provider VARCHAR NOT NULL,
  status VARCHAR NOT NULL DEFAULT 'NOT_CONNECTED',
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  last_sync_at TIMESTAMP,
  last_success_at TIMESTAMP,
  last_error TEXT,
  item_count INTEGER NOT NULL DEFAULT 0,
  metadata_json JSON NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);
CREATE TABLE data_source_sync_runs (
  id VARCHAR PRIMARY KEY,
  provider_id VARCHAR NOT NULL REFERENCES data_sources(id) ON DELETE CASCADE,
  status VARCHAR NOT NULL,
  trace_id VARCHAR NOT NULL,
  idempotency_key VARCHAR NOT NULL,
  fetched_count INTEGER NOT NULL DEFAULT 0,
  inserted_count INTEGER NOT NULL DEFAULT 0,
  updated_count INTEGER NOT NULL DEFAULT 0,
  error_message TEXT,
  started_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP,
  CONSTRAINT uq_provider_sync_idempotency UNIQUE (provider_id, idempotency_key)
);
CREATE TABLE news_items (
  id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, external_id VARCHAR, title TEXT NOT NULL,
  summary TEXT, url TEXT NOT NULL, canonical_url TEXT NOT NULL, author VARCHAR,
  published_at TIMESTAMP, fetched_at TIMESTAMP NOT NULL, content_hash VARCHAR NOT NULL UNIQUE,
  language VARCHAR, sentiment_score NUMERIC(8,6), sentiment_label VARCHAR,
  related_symbols JSON NOT NULL, provenance_json JSON NOT NULL,
  CONSTRAINT uq_news_source_external UNIQUE (source, external_id)
);
CREATE TABLE market_quotes (
  id VARCHAR PRIMARY KEY, symbol VARCHAR NOT NULL, base_asset VARCHAR NOT NULL, quote_asset VARCHAR NOT NULL,
  asset_type VARCHAR NOT NULL, provider VARCHAR NOT NULL, price NUMERIC(38,18), change_24h_pct NUMERIC(20,10),
  volume_24h_base NUMERIC(38,18), volume_24h_quote NUMERIC(38,18), high_24h NUMERIC(38,18),
  low_24h NUMERIC(38,18), bid NUMERIC(38,18), ask NUMERIC(38,18), source_timestamp TIMESTAMP,
  fetched_at TIMESTAMP NOT NULL, provenance_json JSON NOT NULL,
  CONSTRAINT uq_market_quote_source_time UNIQUE (provider, symbol, source_timestamp)
);
CREATE TABLE defi_metrics (
  id VARCHAR PRIMARY KEY, provider VARCHAR NOT NULL, entity_type VARCHAR NOT NULL, entity_id VARCHAR NOT NULL,
  entity_name VARCHAR NOT NULL, chain VARCHAR, metric_type VARCHAR NOT NULL, value NUMERIC(38,18) NOT NULL,
  currency VARCHAR, source_timestamp TIMESTAMP, fetched_at TIMESTAMP NOT NULL, provenance_json JSON NOT NULL,
  CONSTRAINT uq_defi_metric_entity UNIQUE (entity_type, entity_id, chain, metric_type)
);
CREATE TABLE onchain_metrics (
  id VARCHAR PRIMARY KEY, provider VARCHAR NOT NULL, chain VARCHAR NOT NULL, entity_id VARCHAR NOT NULL,
  metric_type VARCHAR NOT NULL, value VARCHAR NOT NULL, block_number INTEGER, source_timestamp TIMESTAMP,
  fetched_at TIMESTAMP NOT NULL, provenance_json JSON NOT NULL,
  CONSTRAINT uq_onchain_metric_entity UNIQUE (provider, chain, entity_id, metric_type)
);

CREATE TABLE agent_conversations (
  id VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title VARCHAR NOT NULL, summary TEXT, status VARCHAR NOT NULL, archived_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
);
CREATE TABLE agent_messages (
  id VARCHAR PRIMARY KEY, conversation_id VARCHAR NOT NULL REFERENCES agent_conversations(id) ON DELETE CASCADE,
  user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE, role VARCHAR NOT NULL, content TEXT NOT NULL,
  status VARCHAR NOT NULL, model VARCHAR, input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0, latency_ms INTEGER, error_code VARCHAR, error_message TEXT,
  created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
);
CREATE TABLE agent_runs (
  id VARCHAR PRIMARY KEY, conversation_id VARCHAR NOT NULL REFERENCES agent_conversations(id) ON DELETE CASCADE,
  user_message_id VARCHAR NOT NULL REFERENCES agent_messages(id) ON DELETE CASCADE,
  assistant_message_id VARCHAR NOT NULL REFERENCES agent_messages(id) ON DELETE CASCADE,
  user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE, model VARCHAR NOT NULL, status VARCHAR NOT NULL,
  started_at TIMESTAMP NOT NULL, completed_at TIMESTAMP, input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0, tool_calls_count INTEGER NOT NULL DEFAULT 0,
  estimated_cost NUMERIC(20,10) NOT NULL DEFAULT 0, trace_id VARCHAR NOT NULL, error_message TEXT,
  usage_recorded BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE agent_tool_calls (
  id VARCHAR PRIMARY KEY, run_id VARCHAR NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  tool_name VARCHAR NOT NULL, arguments_json JSON NOT NULL, result_summary TEXT, status VARCHAR NOT NULL,
  latency_ms INTEGER, error_message TEXT, created_at TIMESTAMP NOT NULL
);
CREATE TABLE agent_message_sources (
  id VARCHAR PRIMARY KEY, message_id VARCHAR NOT NULL REFERENCES agent_messages(id) ON DELETE CASCADE,
  provider VARCHAR NOT NULL, title TEXT NOT NULL, url TEXT, published_at TIMESTAMP,
  source_timestamp TIMESTAMP, fetched_at TIMESTAMP NOT NULL, citation_index INTEGER NOT NULL,
  CONSTRAINT uq_message_citation_index UNIQUE (message_id, citation_index)
);
CREATE TABLE usage_events (
  id VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event_type VARCHAR NOT NULL, quantity INTEGER NOT NULL DEFAULT 1, input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0, metadata_json JSON NOT NULL, idempotency_key VARCHAR NOT NULL UNIQUE,
  created_at TIMESTAMP NOT NULL
);
