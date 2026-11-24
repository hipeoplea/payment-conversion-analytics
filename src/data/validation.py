"""Проверка структуры и связности заказов и платёжных попыток."""

import numpy as np
import pandas as pd

ORDER_COLUMNS = {"order_id", "created_at", "customer_id", "merchant_id", "device", "amount_rub"}
ATTEMPT_COLUMNS = {
    "attempt_id",
    "order_id",
    "attempt_number",
    "created_at",
    "provider",
    "payment_method",
    "status",
    "failure_reason",
    "fee_rub",
}


def validate(orders: pd.DataFrame, attempts: pd.DataFrame) -> None:
    for name, frame, required, identifier in (
        ("orders", orders, ORDER_COLUMNS, "order_id"),
        ("attempts", attempts, ATTEMPT_COLUMNS, "attempt_id"),
    ):
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"{name}: отсутствуют столбцы {sorted(missing)}")
        if frame[identifier].isna().any() or frame[identifier].duplicated().any():
            raise ValueError(f"{name}: {identifier} должен быть уникальным и заполненным")
    if orders["device"].astype("string").fillna("").str.strip().eq("").any():
        raise ValueError("Заказ должен содержать устройство")
    if not orders.empty and (
        not pd.api.types.is_numeric_dtype(orders["amount_rub"])
        or not np.isfinite(orders["amount_rub"]).fillna(False).all()
        or (orders["amount_rub"] <= 0).any()
    ):
        raise ValueError("Заказы должны иметь положительную сумму")
    if attempts["order_id"].isna().any() or not attempts["order_id"].isin(orders["order_id"]).all():
        raise ValueError("Найдены попытки без существующего заказа")
    if not attempts["status"].isin(["succeeded", "failed"]).all():
        raise ValueError("Неизвестный статус платежа")
    for column in ("provider", "payment_method"):
        if attempts[column].astype("string").fillna("").str.strip().eq("").any():
            raise ValueError(f"Попытка должна содержать {column}")
    if not attempts.empty and (
        not pd.api.types.is_numeric_dtype(attempts["fee_rub"])
        or not np.isfinite(attempts["fee_rub"]).fillna(False).all()
        or (attempts["fee_rub"] < 0).any()
    ):
        raise ValueError("Некорректная комиссия")
    if attempts.loc[attempts.status == "failed", "fee_rub"].ne(0).any():
        raise ValueError("Отказ не может приносить комиссию")
    if attempts.loc[attempts.status == "succeeded", "failure_reason"].notna().any():
        raise ValueError("Успешная попытка не может содержать причину отказа")
    failed_reasons = attempts.loc[attempts.status.eq("failed"), "failure_reason"]
    if failed_reasons.astype("string").fillna("").str.strip().eq("").any():
        raise ValueError("Отказ должен содержать причину")
    order_times = pd.to_datetime(orders["created_at"], format="mixed", errors="coerce", utc=True)
    attempt_times = pd.to_datetime(
        attempts["created_at"], format="mixed", errors="coerce", utc=True
    )
    if order_times.isna().any() or attempt_times.isna().any():
        raise ValueError("Заказы и попытки должны иметь корректную дату создания")
    if attempts.empty:
        return

    numbers = attempts["attempt_number"]
    if not pd.api.types.is_numeric_dtype(numbers) or numbers.isna().any():
        raise ValueError("Некорректный номер попытки")
    created_by_order = pd.Series(order_times.array, index=orders["order_id"])
    if attempt_times.lt(attempts["order_id"].map(created_by_order)).any():
        raise ValueError("Попытка оплаты не может предшествовать заказу")

    ordered = attempts.assign(attempt_time=attempt_times).sort_values(
        ["order_id", "attempt_number"]
    )
    groups = ordered.groupby("order_id", sort=False)
    if ordered["attempt_number"].ne(groups.cumcount() + 1).any():
        raise ValueError("Попытки должны нумероваться последовательно с 1")
    if groups["attempt_time"].diff().lt(pd.Timedelta(0)).any():
        raise ValueError("Время попыток должно следовать их порядку")

    success = ordered["status"].eq("succeeded")
    if success.groupby(ordered["order_id"], sort=False).sum().gt(1).any():
        raise ValueError("Один заказ не может быть успешно оплачен дважды")
    if (success & groups.cumcount(ascending=False).gt(0)).any():
        raise ValueError("После успешной оплаты не должно быть новых попыток")
