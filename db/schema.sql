-- SaaS Churn Metric Engine — baseline schema
-- Postgres 16

CREATE TABLE IF NOT EXISTS subscriptions (
    id          SERIAL         PRIMARY KEY,
    customer_id VARCHAR(64)    NOT NULL,
    plan        VARCHAR(64)    NOT NULL,
    mrr         NUMERIC(12, 2) NOT NULL,
    start_date  DATE           NOT NULL,
    end_date    DATE           NULL,        -- NULL = still active; maps to pandas NaT
    status      VARCHAR(16)    NOT NULL
                CHECK (status IN ('active', 'churned')),
    created_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sub_customer_id
    ON subscriptions (customer_id);

CREATE INDEX IF NOT EXISTS idx_sub_status_end_date
    ON subscriptions (status, end_date);

CREATE TABLE IF NOT EXISTS events (
    id          SERIAL       PRIMARY KEY,
    event_id    VARCHAR(64)  NOT NULL UNIQUE,
    customer_id VARCHAR(64)  NOT NULL,
    event_type  VARCHAR(64)  NOT NULL,
    event_date  DATE         NOT NULL,
    metadata    TEXT         NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_customer_id
    ON events (customer_id);

CREATE INDEX IF NOT EXISTS idx_events_event_date
    ON events (event_date);
