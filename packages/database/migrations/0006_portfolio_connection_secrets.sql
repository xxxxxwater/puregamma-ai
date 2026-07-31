ALTER TABLE exchange_connections
ADD COLUMN IF NOT EXISTS credential_ciphertext TEXT;
