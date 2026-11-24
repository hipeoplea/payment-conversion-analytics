import pandas as pd
import pytest

from src.analytics.metrics import calculate, order_metrics_by
from src.analytics.segments import attempts_by_segment, daily_provider_metrics, incident_comparison
from src.data.validation import validate


def example():
    orders = pd.DataFrame(
        {
            "order_id": [1, 2, 3, 4],
            "created_at": pd.to_datetime(["2026-09-01"] * 4),
            "customer_id": [1, 2, 3, 4],
            "merchant_id": [1] * 4,
            "device": ["mobile"] * 4,
            "amount_rub": [100, 200, 300, 400],
        }
    )
    attempts = pd.DataFrame(
        {
            "attempt_id": [1, 2, 3, 4],
            "order_id": [1, 1, 2, 3],
            "attempt_number": [1, 2, 1, 1],
            "created_at": pd.to_datetime(["2026-09-01"] * 4),
            "provider": ["alpha", "beta", "alpha", "beta"],
            "payment_method": ["card"] * 4,
            "status": ["failed", "succeeded", "succeeded", "failed"],
            "failure_reason": ["bank_decline", None, None, "technical_error"],
            "fee_rub": [0.0, 2.0, 4.0, 0.0],
        }
    )
    return orders, attempts


def test_metric_definitions():
    orders, attempts = example()
    validate(orders, attempts)
    metrics = calculate(orders, attempts)
    assert metrics.orders == 4
    assert metrics.orders_with_attempt == 3
    assert metrics.paid_orders == 2
    assert metrics.payment_attempts == 4
    assert metrics.order_conversion == 0.5
    assert metrics.attempt_success_rate == 0.5
    assert metrics.retry_success_rate == 1.0
    assert metrics.gmv_rub == 300
    assert metrics.fee_revenue_rub == 6


def test_segments():
    _, attempts = example()
    result = attempts_by_segment(attempts, "provider").set_index("provider")
    assert result.loc["alpha", "attempts"] == 2
    assert result.loc["alpha", "success_rate"] == 0.5
    with pytest.raises(ValueError):
        attempts_by_segment(attempts, "unknown")


def test_no_double_payment():
    orders, attempts = example()
    attempts.loc[0, "status"] = "succeeded"
    attempts.loc[0, "failure_reason"] = None
    attempts.loc[0, "fee_rub"] = 1
    with pytest.raises(ValueError, match="оплачен дважды"):
        validate(orders, attempts)


def test_funnel_and_retries():
    orders, attempts = example()
    metrics = calculate(orders, attempts)
    assert metrics.first_attempt_paid_orders == 1
    assert metrics.retry_orders == 1
    assert metrics.paid_after_retry == 1
    assert metrics.first_attempt_paid_orders + metrics.paid_after_retry == metrics.paid_orders


def test_orders_without_payment_attempts():
    orders, attempts = example()
    metrics = calculate(orders, attempts.iloc[:0])
    assert metrics.orders == 4
    assert metrics.orders_with_attempt == metrics.paid_orders == 0
    assert metrics.order_conversion == metrics.attempt_success_rate == 0
    assert metrics.retry_success_rate is None
    assert metrics.gmv_rub == metrics.fee_revenue_rub == 0
    assert calculate(orders.iloc[:0], attempts.iloc[:0]).orders == 0


@pytest.mark.parametrize(
    ("row", "column", "value", "message"),
    [
        (0, "created_at", pd.Timestamp("2026-08-31"), "предшествовать заказу"),
        (0, "created_at", pd.NaT, "корректную дату"),
        (0, "attempt_number", 2, "последовательно"),
        (0, "provider", " ", "provider"),
        (0, "failure_reason", "", "причину"),
        (2, "fee_rub", float("inf"), "комиссия"),
        (1, "order_id", 99, "без существующего заказа"),
    ],
)
def test_invalid_payment_data(row, column, value, message):
    orders, attempts = example()
    attempts.loc[row, column] = value
    with pytest.raises(ValueError, match=message):
        validate(orders, attempts)


def test_attempt_times_must_follow_sequence():
    orders, attempts = example()
    attempts.loc[0, "created_at"] = pd.Timestamp("2026-09-01 00:05")
    with pytest.raises(ValueError, match="следовать их порядку"):
        validate(orders, attempts)


def test_no_attempt_after_success():
    orders, attempts = example()
    attempts.loc[0, ["status", "failure_reason", "fee_rub"]] = ["succeeded", None, 1]
    attempts.loc[1, ["status", "failure_reason", "fee_rub"]] = ["failed", "bank_decline", 0]
    with pytest.raises(ValueError, match="После успешной оплаты"):
        validate(orders, attempts)


def test_technical_failure_rate_includes_successes_in_denominator():
    _, attempts = example()
    attempts["failure_reason"] = attempts["failure_reason"].astype("string")
    by_provider = attempts_by_segment(attempts, "provider").set_index("provider")
    daily = daily_provider_metrics(attempts).set_index("provider")
    for result in (by_provider, daily):
        assert result.loc["beta", "technical_failures"] == 1
        assert result.loc["beta", "technical_failure_rate"] == 0.5
        assert result.loc["alpha", "technical_failure_rate"] == 0


def test_incident_windows_are_left_closed_and_right_open():
    _, attempts = example()
    attempts["created_at"] = pd.to_datetime(
        [
            "2026-10-06 00:00",
            "2026-10-12 00:00",
            "2026-10-18 00:00",
            "2026-10-24 00:00",
        ]
    )
    start, end = pd.Timestamp("2026-10-12"), pd.Timestamp("2026-10-18")
    result = incident_comparison(attempts, start, end)
    assert result["period"].tolist() == ["До инцидента", "Во время", "После"]
    assert result["provider"].tolist() == ["alpha", "beta", "alpha"]
    assert result["attempts"].tolist() == [1, 1, 1]
    assert result["success_rate"].tolist() == [0, 1, 1]
    assert incident_comparison(attempts.iloc[:0], start, end).empty


@pytest.mark.parametrize("column", ("date", "device"))
def test_order_segments_match_total_metrics(column):
    orders, attempts = example()
    totals = calculate(orders, attempts)
    segments = order_metrics_by(orders, attempts, column)
    assert segments.orders.sum() == totals.orders
    assert segments.paid_orders.sum() == totals.paid_orders
    assert segments.gmv_rub.sum() == totals.gmv_rub
    assert segments.fee_rub.sum() == totals.fee_revenue_rub
    zero = order_metrics_by(orders, attempts.iloc[:0], column)
    assert zero.paid_orders.sum() == 0
    assert zero.fee_rub.sum() == 0
