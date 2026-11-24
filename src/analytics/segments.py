"""Разрезы для диагностики технических ошибок и успешности операций."""

import pandas as pd

BEFORE, DURING, AFTER = "До инцидента", "Во время", "После"


def with_order_context(orders: pd.DataFrame, attempts: pd.DataFrame) -> pd.DataFrame:
    """Добавляет к попытке устройство и сумму её заказа."""
    return attempts.merge(
        orders[["order_id", "device", "amount_rub"]], on="order_id", validate="many_to_one"
    )


def attempts_by_segment(attempts: pd.DataFrame, column: str) -> pd.DataFrame:
    if column not in {"provider", "payment_method", "attempt_number", "device"}:
        raise ValueError(f"Сегментация по {column!r} не поддерживается")
    return (
        _summarize_attempts(attempts, [column])
        .rename(columns={"successful": "successes"})
        .sort_values("attempts", ascending=False, kind="stable")
    )


def daily_provider_metrics(attempts: pd.DataFrame) -> pd.DataFrame:
    dates = pd.to_datetime(attempts.created_at, format="mixed", utc=True).dt.date
    work = attempts.assign(date=dates)
    return _summarize_attempts(work, ["date", "provider"]).sort_values(
        ["date", "provider"], ignore_index=True
    )


def incident_comparison(
    attempts: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    """Сравнивает одинаковые окна до, во время и после заданного интервала [start, end)."""
    work = attempts.assign(period=incident_period(attempts.created_at, start, end))
    return _summarize_attempts(work, ["period", "provider"])


def incident_period(created_at: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    start = pd.to_datetime(start, utc=True).tz_localize(None)
    end = pd.to_datetime(end, utc=True).tz_localize(None)
    if start >= end:
        raise ValueError("Начало окна должно предшествовать концу")
    width = end - start
    return pd.cut(
        pd.to_datetime(created_at, format="mixed", utc=True).dt.tz_localize(None),
        bins=[start - width, start, end, end + width],
        labels=[BEFORE, DURING, AFTER],
        right=False,
    )


def _summarize_attempts(attempts: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    outcomes = attempts.assign(
        successful=attempts.status.eq("succeeded").fillna(False),
        technical_failure=attempts.failure_reason.eq("technical_error").fillna(False),
    )
    result = outcomes.groupby(keys, as_index=False, observed=True).agg(
        attempts=("attempt_id", "size"),
        successful=("successful", "sum"),
        technical_failures=("technical_failure", "sum"),
    )
    result["success_rate"] = result.successful / result.attempts
    result["technical_failure_rate"] = result.technical_failures / result.attempts
    return result
