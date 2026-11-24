"""Генерация связанных заказов и попыток оплаты; данные полностью синтетические.

Инцидент провайдера beta с 12 по 17 октября заложен специально.
Это известный сценарий симуляции, а не результат исследования реальных данных.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

INCIDENT_PROVIDER = "beta"
INCIDENT_START = pd.Timestamp("2026-10-12")
INCIDENT_END = pd.Timestamp("2026-10-18")
PAYMENT_METHODS = ("card", "sbp", "wallet")
PROVIDERS = ("alpha", "beta")
FAILURE_REASONS = ("bank_decline", "insufficient_funds", "technical_error", "user_cancelled")
FEE_RATES = {"card": 0.022, "sbp": 0.009, "wallet": 0.018}
METHOD_FAILURE_UPLIFT = {"card": 0.06, "sbp": 0.0, "wallet": 0.02}


@dataclass(frozen=True)
class SimulationConfig:
    orders: int = 40_000
    seed: int = 42
    max_attempts: int = 3
    start_date: str = "2026-09-01"
    days: int = 60
    no_attempt_probability: float = 0.04
    retry_probability: float = 0.58
    incident_failure_uplift: float = 0.22

    def __post_init__(self) -> None:
        if self.orders <= 0 or self.max_attempts <= 0 or self.days <= 0:
            raise ValueError("orders, max_attempts и days должны быть положительными")
        if not 0 <= self.no_attempt_probability < 1:
            raise ValueError("no_attempt_probability вне диапазона [0, 1)")
        if not 0 <= self.retry_probability <= 1:
            raise ValueError("retry_probability вне диапазона [0, 1]")
        if not 0 <= self.incident_failure_uplift <= 1:
            raise ValueError("incident_failure_uplift вне диапазона [0, 1]")


def generate(config: SimulationConfig = SimulationConfig()) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Возвращает (orders, attempts), согласованные по идентификаторам заказов."""
    rng = np.random.default_rng(config.seed)
    n = config.orders
    start_date = pd.to_datetime(config.start_date, utc=True).tz_localize(None)
    created_at = start_date + pd.to_timedelta(
        rng.integers(0, config.days * 24 * 60, size=n), unit="m"
    )
    orders = pd.DataFrame(
        {
            "order_id": np.arange(1, n + 1),
            "created_at": created_at,
            "customer_id": rng.integers(1, 15_001, size=n),
            "merchant_id": rng.integers(1, 81, size=n),
            "device": rng.choice(["mobile", "desktop"], n, p=[0.72, 0.28]),
            "amount_rub": np.round(np.clip(rng.lognormal(7.25, 0.8, n), 100, 80_000), 2),
        }
    )
    records: list[dict] = []
    attempt_id = 1
    for order in orders.itertuples(index=False):
        if rng.random() < config.no_attempt_probability:
            continue
        for number in range(1, config.max_attempts + 1):
            method = rng.choice(PAYMENT_METHODS, p=[0.58, 0.32, 0.10])
            provider = rng.choice(PROVIDERS, p=[0.7, 0.3])
            attempt_at = order.created_at + pd.Timedelta(2 * number, unit="min")
            incident = provider == INCIDENT_PROVIDER and INCIDENT_START <= attempt_at < INCIDENT_END
            failure_probability = (
                0.075
                + METHOD_FAILURE_UPLIFT[method]
                + (0.025 if order.device == "mobile" else 0)
                + (config.incident_failure_uplift if incident else 0)
            )
            succeeded = bool(rng.random() >= min(failure_probability, 1.0))
            if succeeded:
                reason = None
            else:
                weights = [0.10, 0.08, 0.75, 0.07] if incident else [0.38, 0.24, 0.23, 0.15]
                reason = str(rng.choice(FAILURE_REASONS, p=weights))
            records.append(
                {
                    "attempt_id": attempt_id,
                    "order_id": int(order.order_id),
                    "attempt_number": number,
                    "created_at": attempt_at,
                    "provider": str(provider),
                    "payment_method": str(method),
                    "status": "succeeded" if succeeded else "failed",
                    "failure_reason": reason,
                    "fee_rub": round(float(order.amount_rub) * FEE_RATES[method], 2)
                    if succeeded
                    else 0.0,
                }
            )
            attempt_id += 1
            if (
                succeeded
                or number == config.max_attempts
                or rng.random() >= config.retry_probability
            ):
                break
    attempts = pd.DataFrame.from_records(
        records,
        columns=[
            "attempt_id",
            "order_id",
            "attempt_number",
            "created_at",
            "provider",
            "payment_method",
            "status",
            "failure_reason",
            "fee_rub",
        ],
    )
    return orders, attempts


def main() -> None:
    parser = argparse.ArgumentParser(description="Создать синтетические заказы и попытки оплаты")
    parser.add_argument("--orders", type=int, default=40_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    orders, attempts = generate(SimulationConfig(orders=args.orders, seed=args.seed))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    orders.to_csv(args.output_dir / "orders.csv", index=False)
    attempts.to_csv(args.output_dir / "payment_attempts.csv", index=False)
    print(f"Создано заказов: {len(orders):,}; попыток оплаты: {len(attempts):,}")


if __name__ == "__main__":
    main()
