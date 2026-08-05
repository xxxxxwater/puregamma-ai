ALTER TABLE user_preferences
ADD COLUMN IF NOT EXISTS portfolio_autopilot_json JSON NOT NULL DEFAULT '{}';
