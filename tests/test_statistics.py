import numpy as np
import pandas as pd
import pytest

from src.analytics.statistics import _clustered_fit, incident_tests, success_intervals


def test_clustered_variance_for_repeated_observations_per_order():
    distinct_orders = 40
    outcome = np.repeat([0.0] * 20 + [1.0] * 20, 3)
    clusters = pd.Series(np.repeat(np.arange(distinct_orders), 3))
    estimate, covariance = _clustered_fit(np.ones((len(outcome), 1)), outcome, clusters)
    assert estimate[0] == pytest.approx(0.5)
    # Копирование наблюдения внутри заказа сохраняет число независимых кластеров.
    assert covariance[0, 0] == pytest.approx(0.25 / (distinct_orders - 1))


def control_sample():
    rows = []
    for provider, date, successes in [
        ("alpha", "2026-10-06", 32),
        ("alpha", "2026-10-12", 28),
        ("alpha", "2026-10-18", 32),
        ("beta", "2026-10-06", 32),
        ("beta", "2026-10-12", 16),
        ("beta", "2026-10-18", 32),
    ]:
        for i in range(40):
            rows.append(
                {
                    "order_id": len(rows),
                    "provider": provider,
                    "created_at": date,
                    "status": "succeeded" if i < successes else "failed",
                    "payment_method": "card",
                    "device": "mobile",
                    "amount_rub": 100,
                    "attempt_number": 1,
                }
            )
    return pd.DataFrame(rows)


def test_difference_in_differences_and_intervals():
    sample = control_sample()
    results = incident_tests(sample).set_index("comparison")
    assert results.loc["DiD, во время сбоя", "estimate"] == pytest.approx(-0.3)
    assert results.loc["DiD, после сбоя", "estimate"] == pytest.approx(0, abs=1e-10)
    assert results.loc["DiD, во время сбоя с поправкой на состав", "estimate"] == pytest.approx(
        -0.3
    )
    assert 0 < results.loc["DiD, во время сбоя", "p_value"] < 0.05
    rate = success_intervals(sample).set_index(["period", "provider"]).loc[("Во время", "beta")]
    assert rate.estimate == pytest.approx(0.4)
    assert 0 < rate.low < rate.estimate < rate.high < 1


def test_empty_and_sparse_samples():
    sample = control_sample()
    assert success_intervals(sample.iloc[:0]).empty
    assert incident_tests(sample.iloc[:0]).empty
    sparse = success_intervals(sample.iloc[:3])
    assert sparse.low.isna().all()
    assert sparse.high.isna().all()
    assert incident_tests(sample.loc[sample.provider.eq("alpha")]).empty
