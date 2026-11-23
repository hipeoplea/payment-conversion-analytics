"""Generate reproducible synthetic *payment attempts*, not real bank data."""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd

METHODS = ["card", "sbp", "wallet"]
DEVICES = ["mobile", "desktop"]
FAILURES = ["bank_decline", "insufficient_funds", "technical_error", "user_cancelled"]

def generate(n: int = 100_000, seed: int = 42) -> pd.DataFrame:
    if n < 1:
        raise ValueError("n must be positive")
    rng = np.random.default_rng(seed)
    merchants = rng.integers(1, 81, size=n)
    customers = rng.integers(1, 20_001, size=n)
    methods = rng.choice(METHODS, size=n, p=[0.57, 0.33, 0.10])
    devices = rng.choice(DEVICES, size=n, p=[0.73, 0.27])
    timestamps = pd.Timestamp("2026-09-01") + pd.to_timedelta(
        rng.integers(0, 60 * 24 * 60, size=n), unit="m"
    )
    amount = np.round(np.clip(rng.lognormal(7.3, 0.86, n), 100, 80_000), 2)
    provider = rng.choice(["alpha", "beta"], size=n, p=[0.7, 0.3])

    # Explicitly injected scenario: provider beta has technical issues on Oct 12-17.
    incident = (
        (provider == "beta")
        & (timestamps >= pd.Timestamp("2026-10-12"))
        & (timestamps < pd.Timestamp("2026-10-18"))
    )
    fail_prob = (
        0.075
        + np.where(methods == "card", 0.055, np.where(methods == "wallet", 0.02, 0))
        + np.where(devices == "mobile", 0.025, 0)
        + np.where(incident, 0.18, 0)
    )
    failed = rng.random(n) < fail_prob
    causes = rng.choice(FAILURES, size=n, p=[0.38, 0.24, 0.23, 0.15]).astype(object)
    causes[incident & failed] = rng.choice(
        FAILURES, size=int((incident & failed).sum()), p=[0.1, 0.08, 0.75, 0.07]
    )
    causes[~failed] = None
    # Fee is earned only on successful payments. No invented revenue on declines.
    fee_rate = np.where(methods == "sbp", 0.009, np.where(methods == "wallet", 0.018, 0.022))
    fee = np.round(np.where(failed, 0, amount * fee_rate), 2)

    df = pd.DataFrame({
        "attempt_id": np.arange(1, n + 1),
        "created_at": timestamps,
        "merchant_id": merchants,
        "customer_id": customers,
        "provider": provider,
        "payment_method": methods,
        "device": devices,
        "amount_rub": amount,
        "status": np.where(failed, "failed", "succeeded"),
        "failure_reason": causes,
        "fee_rub": fee,
    })
    return df.sort_values(["created_at", "attempt_id"]).reset_index(drop=True)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=Path("data/payment_attempts.csv"))
    args = parser.parse_args()
    df = generate(args.rows, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"Generated {len(df):,} synthetic attempts: {args.output}")

if __name__ == "__main__":
    main()
