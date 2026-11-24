"""Сценарии по заказам, начавшим оплату через beta в окно сбоя."""

import pandas as pd

from src.analytics.segments import AFTER, BEFORE, DURING, incident_period
from src.data.generator import FEE_RATES, INCIDENT_END, INCIDENT_START

MIN_SEGMENT_ORDERS = 20
SEGMENT = ["payment_method", "device"]
OUTCOME_COLUMNS = ["reference_rate", "additional_paid_orders", "gmv_rub", "fee_rub"]


def _reference(first: pd.DataFrame, provider: str, periods: list[str]) -> pd.Series:
    work = first.loc[first.provider.eq(provider) & first.period.isin(periods)]
    stats = work.groupby(SEGMENT, observed=True).paid.agg(["size", "mean"])
    return stats["mean"].where(stats["size"].ge(MIN_SEGMENT_ORDERS))


def _scenario(
    case: pd.DataFrame,
    benchmark: pd.Series,
    coverage: float = 1.0,
) -> dict[str, float]:
    """Дополнительный успех распределяется среди фактически неоплаченных заказов."""
    observed = case["beta_during"]
    conditional = (
        ((benchmark - observed).clip(lower=0) / (1 - observed).replace(0, float("nan")))
        .clip(upper=1)
        .fillna(0)
    )
    weight = conditional * (~case.paid) * coverage
    return {
        "reference_rate": float(benchmark.mean()),
        "additional_paid_orders": float(weight.sum()),
        "gmv_rub": float((weight * case.amount_rub).sum()),
        "fee_rub": float((weight * case.modeled_fee).sum()),
    }


def estimate_impact(attempts: pd.DataFrame) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """Восстанавливает исход заказа по всей истории, затем назначает когорту первой попытки."""
    dates = incident_period(attempts.created_at, INCIDENT_START, INCIDENT_END)
    paid_ids = attempts.loc[attempts.status.eq("succeeded"), "order_id"]
    first = attempts.loc[attempts.attempt_number.eq(1)].assign(
        period=dates, paid=lambda frame: frame.order_id.isin(paid_ids)
    )
    incident_beta = attempts.loc[dates.eq(DURING) & attempts.provider.eq("beta")]
    failed_beta = incident_beta.loc[incident_beta.status.eq("failed")]
    case = first.loc[first.provider.eq("beta") & first.period.eq(DURING)].copy()
    case["modeled_fee"] = (case.amount_rub * case.payment_method.map(FEE_RATES)).round(2)
    references = (
        ("beta_before", "beta", [BEFORE]),
        ("beta_during", "beta", [DURING]),
        ("beta_after", "beta", [AFTER]),
        ("beta_pooled", "beta", [BEFORE, AFTER]),
        ("alpha_before", "alpha", [BEFORE]),
        ("alpha_during", "alpha", [DURING]),
    )
    for name, provider, periods in references:
        rate = _reference(first, provider, periods).rename(name)
        case = case.join(rate, on=SEGMENT)

    # Одинаковый набор поддержанных сегментов для сравнимости сценариев.
    supported = case.dropna(subset=[name for name, _, _ in references] + ["modeled_fee"])
    routing_eligible = supported.loc[supported.alpha_during.gt(supported.beta_during)]
    facts = {
        "cohort_orders": len(case),
        "paid_orders": int(case.paid.sum()),
        "unpaid_orders": int((~case.paid).sum()),
        "unpaid_gmv_rub": float(case.loc[~case.paid, "amount_rub"].sum()),
        "failed_attempts": len(failed_beta),
        "gross_failed_attempt_amount_rub": float(failed_beta.amount_rub.sum()),
        "supported_orders": len(supported),
        "routing_eligible_orders": len(routing_eligible),
        "observed_rate": float(case.paid.mean()) if len(case) else None,
    }

    candidates = {
        "Консервативный": (supported.beta_before + supported.alpha_during - supported.alpha_before)
        .clip(0, 1)
        .clip(upper=supported.beta_pooled),
        "Базовый": supported.beta_pooled,
        "Оптимистичный": supported[["beta_before", "beta_after"]].max(axis=1),
    }
    scenarios = [
        {"scenario": label, **_scenario(supported, benchmark)}
        for label, benchmark in candidates.items()
        if not supported.empty
    ]
    routing = [
        {"coverage": share, **_scenario(routing_eligible, routing_eligible.alpha_during, share)}
        for share in (0.25, 0.50, 0.75)
        if not routing_eligible.empty
    ]
    return (
        facts,
        pd.DataFrame(scenarios, columns=["scenario", *OUTCOME_COLUMNS]),
        pd.DataFrame(routing, columns=["coverage", *OUTCOME_COLUMNS]),
    )
