"""Definitions deliberately use *attempts* as denominator, not unique users."""
import pandas as pd

REQUIRED = {"attempt_id", "created_at", "amount_rub", "status", "fee_rub"}

def validate(df: pd.DataFrame) -> None:
    missing = REQUIRED.difference(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    if df["attempt_id"].isna().any() or df["attempt_id"].duplicated().any():
        raise ValueError("attempt_id must be unique and non-null")
    if not df["status"].isin(["succeeded", "failed"]).all():
        raise ValueError("Unknown payment status")
    if (df["amount_rub"] <= 0).any() or (df["fee_rub"] < 0).any():
        raise ValueError("Invalid amount or fee")
    if (df.loc[df.status == "failed", "fee_rub"] != 0).any():
        raise ValueError("Failed payments must not generate fees")

def summary(df: pd.DataFrame) -> dict:
    validate(df)
    ok = df["status"].eq("succeeded")
    attempts = len(df)
    return {
        "attempts": attempts,
        "successful": int(ok.sum()),
        "payment_success_rate": float(ok.mean()) if attempts else 0.0,
        "gmv_rub": float(df.loc[ok, "amount_rub"].sum()),
        "fee_revenue_rub": float(df.loc[ok, "fee_rub"].sum()),
        "failed_requested_amount_rub": float(df.loc[~ok, "amount_rub"].sum()),
    }

def by_segment(df: pd.DataFrame, column: str) -> pd.DataFrame:
    validate(df)
    if column not in df.columns:
        raise ValueError(f"Unknown segment: {column}")
    result = df.assign(
        succeeded=df.status.eq("succeeded").astype(int),
        successful_gmv=df.amount_rub.where(df.status.eq("succeeded"), 0),
    ).groupby(column, dropna=False).agg(
        attempts=("attempt_id", "count"),
        successful=("succeeded", "sum"),
        gmv_rub=("successful_gmv", "sum"),
    ).reset_index()
    result["success_rate"] = result["successful"] / result["attempts"]
    return result.sort_values("attempts", ascending=False)

def daily(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["date"] = pd.to_datetime(work["created_at"]).dt.date
    return by_segment(work, "date").sort_values("date")
