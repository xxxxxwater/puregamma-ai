CREATE TABLE IF NOT EXISTS portfolio_autopilot_reviews (
  id VARCHAR PRIMARY KEY,
  user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  nav FLOAT NOT NULL DEFAULT 0,
  account_count INTEGER NOT NULL DEFAULT 0,
  findings_json JSON NOT NULL DEFAULT '[]',
  concentration_json JSON NOT NULL DEFAULT '{}',
  status VARCHAR NOT NULL DEFAULT 'COMPLETED',
  data_as_of TIMESTAMP NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_portfolio_autopilot_reviews_user_id ON portfolio_autopilot_reviews(user_id);
CREATE INDEX IF NOT EXISTS ix_portfolio_autopilot_reviews_status ON portfolio_autopilot_reviews(status);
