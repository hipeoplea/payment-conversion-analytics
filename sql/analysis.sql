-- PostgreSQL 15+. Import data/payment_attempts.csv to payment_attempts first.
CREATE TABLE IF NOT EXISTS payment_attempts (
  attempt_id bigint PRIMARY KEY,
  created_at timestamp NOT NULL,
  merchant_id integer NOT NULL,
  customer_id integer NOT NULL,
  provider text NOT NULL,
  payment_method text NOT NULL,
  device text NOT NULL,
  amount_rub numeric(14,2) NOT NULL CHECK (amount_rub > 0),
  status text NOT NULL CHECK (status IN ('succeeded', 'failed')),
  failure_reason text,
  fee_rub numeric(14,2) NOT NULL CHECK (fee_rub >= 0),
  CHECK ((status = 'succeeded' AND failure_reason IS NULL) OR
         (status = 'failed' AND failure_reason IS NOT NULL AND fee_rub = 0))
);

-- One row = one payment attempt. Multiple attempts may belong to one customer.
SELECT COUNT(*) AS attempts,
       COUNT(*) FILTER (WHERE status = 'succeeded') AS successful,
       ROUND(COUNT(*) FILTER (WHERE status = 'succeeded')::numeric / NULLIF(COUNT(*),0), 4) AS success_rate,
       SUM(amount_rub) FILTER (WHERE status = 'succeeded') AS gmv_rub,
       SUM(fee_rub) AS fee_revenue_rub
FROM payment_attempts;

-- Daily success-rate diagnostics per provider.
SELECT created_at::date AS payment_date, provider,
       COUNT(*) AS attempts,
       ROUND(AVG((status = 'succeeded')::integer), 4) AS success_rate,
       COUNT(*) FILTER (WHERE failure_reason = 'technical_error') AS technical_declines
FROM payment_attempts
GROUP BY 1, 2 ORDER BY 1, 2;

-- Most common reasons for failure.
SELECT failure_reason, COUNT(*) AS failures,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_failures
FROM payment_attempts WHERE status = 'failed'
GROUP BY failure_reason ORDER BY failures DESC;

-- Potentially retryable technical failures are NOT guaranteed recoverable revenue.
SELECT provider, COUNT(*) AS technical_failures,
       SUM(amount_rub) AS requested_amount_at_risk_rub
FROM payment_attempts WHERE failure_reason = 'technical_error'
GROUP BY provider ORDER BY technical_failures DESC;
