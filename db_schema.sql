CREATE TABLE IF NOT EXISTS sync_state (
    id SERIAL PRIMARY KEY,
    last_history_id VARCHAR,
    watch_expiration TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS notified_messages (
    id SERIAL PRIMARY KEY,
    message_id VARCHAR NOT NULL UNIQUE,
    attempted_at TIMESTAMPTZ,
    notified_at TIMESTAMPTZ
);
