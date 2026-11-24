import pandas as pd
import pytest

from src.analytics.impact import estimate_impact


def control_sample():
    rows = []
    for provider, date, successes in [
        ("alpha", "2026-10-06", 16),
        ("alpha", "2026-10-12", 16),
        ("beta", "2026-10-06", 16),
        ("beta", "2026-10-12", 10),
        ("beta", "2026-10-18", 16),
    ]:
        for i in range(20):
            rows.append(
                {
                    "order_id": len(rows),
                    "created_at": date,
                    "device": "mobile",
                    "provider": provider,
                    "attempt_number": 1,
                    "payment_method": "card",
                    "amount_rub": 100.0,
                    "status": "succeeded" if i < successes else "failed",
                }
            )
    return pd.DataFrame(rows)


def test_scenarios_use_final_order_outcomes_and_do_not_double_count():
    sample = control_sample()
    failed_first = sample.loc[
        sample.provider.eq("beta") & sample.created_at.eq("2026-10-12") & sample.status.eq("failed")
    ]
    retries = failed_first.iloc[:2].assign(
        attempt_number=2, provider=["alpha", "beta"], status=["succeeded", "failed"]
    )
    sample = pd.concat([sample, retries], ignore_index=True)
    facts, scenarios, routing = estimate_impact(sample)

    assert facts["cohort_orders"] == 20
    assert facts["paid_orders"] == 11
    assert facts["unpaid_orders"] == 9
    assert facts["unpaid_gmv_rub"] == 900
    assert facts["failed_attempts"] == 11
    assert facts["gross_failed_attempt_amount_rub"] == 1100
    base = scenarios.set_index("scenario").loc["Базовый"]
    assert base.reference_rate == pytest.approx(0.8)
    assert base.additional_paid_orders == pytest.approx(5)
    assert base.gmv_rub == pytest.approx(500)
    assert base.fee_rub == pytest.approx(11)
    pilot = routing.set_index("coverage").loc[0.25]
    assert pilot.additional_paid_orders == pytest.approx(1.25)
    assert pilot.gmv_rub == pytest.approx(125)


def test_unsupported_segment_is_excluded_from_effect():
    sample = control_sample()
    sample.loc[0, "device"] = "desktop"
    facts, scenarios, routing = estimate_impact(sample)
    assert facts["cohort_orders"] == 20
    assert facts["supported_orders"] == 0
    assert scenarios.empty and routing.empty
    assert estimate_impact(sample.iloc[:0])[0]["cohort_orders"] == 0
