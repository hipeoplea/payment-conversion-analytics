"""Единые определения платёжных и продуктовых показателей."""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class PaymentMetrics:
    orders: int
    orders_with_attempt: int
    paid_orders: int
    payment_attempts: int
    succeeded_attempts: int
    order_conversion: float
    attempt_success_rate: float
    retry_success_rate: float | None
    gmv_rub: float
    fee_revenue_rub: float
    first_attempt_paid_orders: int
    retry_orders: int
    paid_after_retry: int


def calculate(orders: pd.DataFrame, attempts: pd.DataFrame) -> PaymentMetrics:
    """Считает метрики по связанным таблицам, прошедшим валидацию."""
    success = attempts.status.eq("succeeded")
    paid_ids = set(attempts.loc[success, "order_id"])
    attempted_ids = set(attempts["order_id"])
    paid = orders["order_id"].isin(paid_ids)
    retry_orders = set(attempts.loc[attempts.attempt_number.gt(1), "order_id"])
    recovered = retry_orders.intersection(paid_ids)
    n_orders, n_attempts = len(orders), len(attempts)
    return PaymentMetrics(
        orders=n_orders,
        orders_with_attempt=len(attempted_ids),
        paid_orders=int(paid.sum()),
        payment_attempts=n_attempts,
        succeeded_attempts=int(success.sum()),
        order_conversion=float(paid.mean()) if n_orders else 0.0,
        attempt_success_rate=float(success.mean()) if n_attempts else 0.0,
        retry_success_rate=len(recovered) / len(retry_orders) if retry_orders else None,
        gmv_rub=float(orders.loc[paid, "amount_rub"].sum()),
        fee_revenue_rub=float(attempts.loc[success, "fee_rub"].sum()),
        first_attempt_paid_orders=int((success & attempts.attempt_number.eq(1)).sum()),
        retry_orders=len(retry_orders),
        paid_after_retry=len(recovered),
    )


def order_metrics_by(orders: pd.DataFrame, attempts: pd.DataFrame, column: str) -> pd.DataFrame:
    """Агрегирует по устройству или дате создания заказа, сохраняя заказы без попыток."""
    if column not in {"device", "date"}:
        raise ValueError(f"Сегментация заказов по {column!r} не поддерживается")
    successful = attempts.loc[attempts.status.eq("succeeded")].set_index("order_id")
    paid = orders.order_id.isin(successful.index)
    work = orders.assign(
        paid=paid,
        gmv_rub=orders.amount_rub.where(paid, 0),
        fee_rub=orders.order_id.map(successful.fee_rub).fillna(0).astype(float),
    )
    if column == "date":
        work["date"] = pd.to_datetime(orders.created_at, format="mixed", utc=True).dt.date
    result = work.groupby(column, as_index=False, observed=True).agg(
        orders=("order_id", "size"),
        paid_orders=("paid", "sum"),
        gmv_rub=("gmv_rub", "sum"),
        fee_rub=("fee_rub", "sum"),
    )
    result["order_conversion"] = result.paid_orders / result.orders
    return result
