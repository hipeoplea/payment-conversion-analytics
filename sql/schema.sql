-- PostgreSQL 15+: связанные заказы и попытки оплаты.
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    customer_id BIGINT NOT NULL,
    merchant_id INTEGER NOT NULL,
    device TEXT NOT NULL,
    amount_rub NUMERIC(14,2) NOT NULL CHECK (amount_rub > 0)
);

CREATE TABLE payment_attempts (
    attempt_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
    created_at TIMESTAMP NOT NULL,
    provider TEXT NOT NULL,
    payment_method TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('succeeded', 'failed')),
    failure_reason TEXT,
    fee_rub NUMERIC(14,2) NOT NULL CHECK (fee_rub >= 0),
    UNIQUE (order_id, attempt_number),
    CHECK ((status = 'succeeded' AND failure_reason IS NULL) OR
           (status = 'failed' AND failure_reason IS NOT NULL AND fee_rub = 0))
);
CREATE INDEX idx_attempts_created_provider ON payment_attempts (created_at, provider);
CREATE UNIQUE INDEX idx_attempts_one_success_per_order
    ON payment_attempts (order_id) WHERE status = 'succeeded';
