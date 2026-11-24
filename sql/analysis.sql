-- 1. Воронка, конверсия заказов, GMV и комиссии.
-- Сначала сворачиваем попытки до одной строки на заказ, затем соединяем все заказы.
WITH order_payments AS (
    SELECT order_id,
           BOOL_OR(status = 'succeeded') AS paid,
           BOOL_OR(status = 'succeeded' AND attempt_number = 1) AS paid_first,
           BOOL_OR(attempt_number > 1) AS retried,
           SUM(fee_rub) FILTER (WHERE status = 'succeeded') AS fees_rub
    FROM payment_attempts
    GROUP BY order_id
)
SELECT COUNT(*) AS orders_total,
       COUNT(p.order_id) AS orders_with_attempt,
       COUNT(*) FILTER (WHERE p.paid) AS paid_orders,
       COUNT(*) FILTER (WHERE p.paid_first) AS first_attempt_paid_orders,
       COUNT(*) FILTER (WHERE p.retried) AS retry_orders,
       COUNT(*) FILTER (WHERE p.paid AND p.retried) AS paid_after_retry,
       COALESCE(ROUND(COUNT(*) FILTER (WHERE p.paid)::NUMERIC
           / NULLIF(COUNT(*), 0), 6), 0) AS order_conversion,
       ROUND(COUNT(*) FILTER (WHERE p.paid AND p.retried)::NUMERIC
           / NULLIF(COUNT(*) FILTER (WHERE p.retried), 0), 6) AS retry_success_rate,
       COALESCE(SUM(o.amount_rub) FILTER (WHERE p.paid), 0) AS gmv_rub,
       COALESCE(SUM(p.fees_rub), 0) AS fee_revenue_rub
FROM orders AS o
LEFT JOIN order_payments AS p USING (order_id);

-- 2. Общая успешность попыток. Успешные попытки входят в знаменатель техотказов.
SELECT COUNT(*) AS attempts,
       COUNT(*) FILTER (WHERE status = 'succeeded') AS successful,
       COUNT(*) FILTER (WHERE failure_reason = 'technical_error') AS technical_failures,
       COALESCE(ROUND(COUNT(*) FILTER (WHERE status = 'succeeded')::NUMERIC
           / NULLIF(COUNT(*), 0), 6), 0) AS success_rate,
       COALESCE(ROUND(COUNT(*) FILTER (WHERE failure_reason = 'technical_error')::NUMERIC
           / NULLIF(COUNT(*), 0), 6), 0) AS technical_failure_rate
FROM payment_attempts;

-- 3. Сравнение провайдеров и методов оплаты.
SELECT provider, payment_method,
       COUNT(*) AS attempts,
       COUNT(*) FILTER (WHERE status = 'succeeded') AS successful,
       COUNT(*) FILTER (WHERE failure_reason = 'technical_error') AS technical_failures,
       ROUND(COUNT(*) FILTER (WHERE status = 'succeeded')::NUMERIC / COUNT(*), 6) AS success_rate,
       ROUND(COUNT(*) FILTER (WHERE failure_reason = 'technical_error')::NUMERIC
           / COUNT(*), 6) AS technical_failure_rate
FROM payment_attempts
GROUP BY GROUPING SETS ((provider), (payment_method))
ORDER BY provider NULLS LAST, attempts DESC;

-- 4. Динамика по дате попытки и провайдеру.
SELECT created_at::DATE AS day, provider,
       COUNT(*) AS attempts,
       COUNT(*) FILTER (WHERE status = 'succeeded') AS successful,
       COUNT(*) FILTER (WHERE failure_reason = 'technical_error') AS technical_failures,
       ROUND(COUNT(*) FILTER (WHERE status = 'succeeded')::NUMERIC / COUNT(*), 6) AS success_rate,
       ROUND(COUNT(*) FILTER (WHERE failure_reason = 'technical_error')::NUMERIC
           / COUNT(*), 6) AS technical_failure_rate
FROM payment_attempts
GROUP BY 1, 2
ORDER BY 1, 2;

-- 5. Симуляция сбоя beta. Соседние окна той же длины, границы [начало, конец).
WITH windows (position, period, start_at, end_at) AS (
    VALUES
        (1, 'До инцидента', TIMESTAMP '2026-10-06', TIMESTAMP '2026-10-12'),
        (2, 'Во время', TIMESTAMP '2026-10-12', TIMESTAMP '2026-10-18'),
        (3, 'После', TIMESTAMP '2026-10-18', TIMESTAMP '2026-10-24')
)
SELECT w.period, a.provider,
       COUNT(*) AS attempts,
       COUNT(*) FILTER (WHERE a.status = 'succeeded') AS successful,
       COUNT(*) FILTER (WHERE a.failure_reason = 'technical_error') AS technical_failures,
       ROUND(COUNT(*) FILTER (WHERE a.status = 'succeeded')::NUMERIC / COUNT(*), 6) AS success_rate,
       ROUND(COUNT(*) FILTER (WHERE a.failure_reason = 'technical_error')::NUMERIC
           / COUNT(*), 6) AS technical_failure_rate
FROM windows AS w
JOIN payment_attempts AS a ON a.created_at >= w.start_at AND a.created_at < w.end_at
GROUP BY w.position, w.period, a.provider
ORDER BY w.position, a.provider;

-- 6. Заказы по устройству и по дате их создания. Одна строка на заказ.
SELECT o.device, o.created_at::DATE AS day,
       COUNT(*) AS orders,
       COUNT(a.attempt_id) AS paid_orders,
       ROUND(COUNT(a.attempt_id)::NUMERIC / COUNT(*), 6) AS order_conversion,
       COALESCE(SUM(o.amount_rub) FILTER (WHERE a.attempt_id IS NOT NULL), 0) AS gmv_rub,
       COALESCE(SUM(a.fee_rub), 0) AS fee_rub
FROM orders AS o
LEFT JOIN payment_attempts AS a ON a.order_id = o.order_id AND a.status = 'succeeded'
GROUP BY GROUPING SETS ((o.device), (o.created_at::DATE))
ORDER BY device NULLS LAST, day;

-- 7. Попытки по устройству и порядковому номеру.
SELECT o.device, a.attempt_number,
       COUNT(*) AS attempts,
       COUNT(*) FILTER (WHERE a.status = 'succeeded') AS successful,
       COUNT(*) FILTER (WHERE a.failure_reason = 'technical_error') AS technical_failures,
       ROUND(COUNT(*) FILTER (WHERE a.status = 'succeeded')::NUMERIC / COUNT(*), 6) AS success_rate,
       ROUND(COUNT(*) FILTER (WHERE a.failure_reason = 'technical_error')::NUMERIC
           / COUNT(*), 6) AS technical_failure_rate
FROM payment_attempts AS a
JOIN orders AS o USING (order_id)
GROUP BY GROUPING SETS ((o.device), (a.attempt_number))
ORDER BY device NULLS LAST, attempt_number;
