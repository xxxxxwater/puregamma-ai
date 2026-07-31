-- Unified licensed document-source pipeline for RSS, FinTwit, X, and Bloomberg.
CREATE TABLE sources (
  id VARCHAR PRIMARY KEY, provider VARCHAR NOT NULL, provider_type VARCHAR NOT NULL,
  external_key VARCHAR NOT NULL, name VARCHAR NOT NULL, source_url TEXT, language VARCHAR NOT NULL DEFAULT 'en',
  enabled BOOLEAN NOT NULL DEFAULT TRUE, credibility_score FLOAT NOT NULL DEFAULT 0.5,
  source_license VARCHAR NOT NULL DEFAULT 'unknown', redistribution_allowed BOOLEAN NOT NULL DEFAULT FALSE,
  retention_policy VARCHAR NOT NULL DEFAULT 'configured', config_json JSON NOT NULL,
  created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL,
  CONSTRAINT uq_source_provider_external UNIQUE (provider, external_key)
);
CREATE INDEX ix_sources_provider ON sources(provider);

CREATE TABLE raw_documents (
  id VARCHAR PRIMARY KEY, source_id VARCHAR NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  provider VARCHAR NOT NULL, external_id VARCHAR NOT NULL, cursor TEXT, content_hash VARCHAR NOT NULL UNIQUE,
  raw_payload JSON NOT NULL, source_url TEXT, published_at TIMESTAMP, fetched_at TIMESTAMP NOT NULL,
  license_status VARCHAR NOT NULL DEFAULT 'unknown', retention_policy VARCHAR NOT NULL DEFAULT 'configured',
  processing_status VARCHAR NOT NULL DEFAULT 'pending', created_at TIMESTAMP NOT NULL,
  CONSTRAINT uq_raw_provider_external UNIQUE (provider, external_id)
);
CREATE INDEX ix_raw_documents_provider ON raw_documents(provider);
CREATE INDEX ix_raw_documents_fetched_at ON raw_documents(fetched_at);

CREATE TABLE normalized_documents (
  id VARCHAR PRIMARY KEY, raw_document_id VARCHAR NOT NULL UNIQUE REFERENCES raw_documents(id) ON DELETE CASCADE,
  source_id VARCHAR NOT NULL REFERENCES sources(id) ON DELETE CASCADE, provider VARCHAR NOT NULL,
  source_type VARCHAR NOT NULL, source_name VARCHAR NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL,
  summary TEXT NOT NULL, url TEXT, author VARCHAR, published_at TIMESTAMP, language VARCHAR NOT NULL DEFAULT 'en',
  symbols JSON NOT NULL, topics JSON NOT NULL, sentiment JSON NOT NULL, credibility_score FLOAT NOT NULL DEFAULT 0.5,
  engagement_metrics JSON NOT NULL, raw_payload JSON NOT NULL, license_status VARCHAR NOT NULL DEFAULT 'unknown',
  retention_policy VARCHAR NOT NULL DEFAULT 'configured', redistribution_allowed BOOLEAN NOT NULL DEFAULT FALSE,
  stable_hash VARCHAR NOT NULL UNIQUE, event_fingerprint VARCHAR NOT NULL, final_score FLOAT NOT NULL DEFAULT 0,
  alert_processed_at TIMESTAMP, created_at TIMESTAMP NOT NULL
);
CREATE INDEX ix_normalized_documents_provider ON normalized_documents(provider);
CREATE INDEX ix_normalized_documents_published_at ON normalized_documents(published_at);
CREATE INDEX ix_normalized_documents_event_fingerprint ON normalized_documents(event_fingerprint);

CREATE TABLE entity_mentions (
  id VARCHAR PRIMARY KEY, document_id VARCHAR NOT NULL REFERENCES normalized_documents(id) ON DELETE CASCADE,
  symbol VARCHAR NOT NULL, mention_text VARCHAR, relevance_score FLOAT NOT NULL DEFAULT 0.5,
  created_at TIMESTAMP NOT NULL, CONSTRAINT uq_document_entity_symbol UNIQUE (document_id, symbol)
);
CREATE INDEX ix_entity_mentions_symbol ON entity_mentions(symbol);

CREATE TABLE sentiment_signals (
  id VARCHAR PRIMARY KEY, document_id VARCHAR NOT NULL UNIQUE REFERENCES normalized_documents(id) ON DELETE CASCADE,
  sentiment_score FLOAT NOT NULL, sentiment_label VARCHAR NOT NULL, source_credibility FLOAT NOT NULL,
  freshness_score FLOAT NOT NULL, engagement_score FLOAT NOT NULL, asset_relevance FLOAT NOT NULL,
  final_score FLOAT NOT NULL, event_fingerprint VARCHAR NOT NULL, created_at TIMESTAMP NOT NULL
);
CREATE INDEX ix_sentiment_signals_event_fingerprint ON sentiment_signals(event_fingerprint);

CREATE TABLE provider_sync_logs (
  id VARCHAR PRIMARY KEY, provider_id VARCHAR NOT NULL REFERENCES data_sources(id) ON DELETE CASCADE,
  status VARCHAR NOT NULL, idempotency_key VARCHAR NOT NULL, cursor_before TEXT, cursor_after TEXT,
  fetched_count INTEGER NOT NULL DEFAULT 0, inserted_count INTEGER NOT NULL DEFAULT 0,
  duplicate_count INTEGER NOT NULL DEFAULT 0, retry_count INTEGER NOT NULL DEFAULT 0,
  http_status INTEGER, rate_limit_reset_at TIMESTAMP, error_code VARCHAR, error_message TEXT,
  usage_json JSON NOT NULL, started_at TIMESTAMP NOT NULL, completed_at TIMESTAMP,
  CONSTRAINT uq_provider_log_idempotency UNIQUE (provider_id, idempotency_key)
);

CREATE TABLE fintwit_accounts (
  id VARCHAR PRIMARY KEY, username VARCHAR NOT NULL, display_name VARCHAR NOT NULL, platform VARCHAR NOT NULL DEFAULT 'x',
  category VARCHAR NOT NULL, language VARCHAR NOT NULL DEFAULT 'en', credibility_score FLOAT NOT NULL DEFAULT 0.6,
  account_weight FLOAT NOT NULL DEFAULT 1, historical_accuracy FLOAT, enabled BOOLEAN NOT NULL DEFAULT TRUE,
  source_url TEXT, provider_user_id VARCHAR, collection_method VARCHAR NOT NULL DEFAULT 'official_api',
  created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL,
  CONSTRAINT uq_fintwit_platform_username UNIQUE (platform, username)
);
CREATE INDEX ix_fintwit_accounts_username ON fintwit_accounts(username);
