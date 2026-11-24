"""Сравнение долей с кластерными стандартными ошибками на уровне заказа."""

from math import erfc, sqrt
from statistics import NormalDist

import numpy as np
import pandas as pd

from src.analytics.segments import AFTER, BEFORE, DURING, incident_period
from src.data.generator import INCIDENT_END, INCIDENT_START

INCIDENT_DID = "DiD, во время сбоя"
MIN_CLUSTERS = 30
Z_95 = NormalDist().inv_cdf(0.975)
COMPARISON_COLUMNS = ["comparison", "estimate", "low", "high", "p_value"]
RATE_COLUMNS = ["period", "provider", "attempts", "orders", "estimate", "low", "high"]


def _clustered_fit(
    design: np.ndarray, outcome: np.ndarray, order_ids: pd.Series
) -> tuple[np.ndarray, np.ndarray | None]:
    """OLS и кластерная ковариация CR1. Асимптотика предполагает независимость заказов."""
    coefficients, _, rank, _ = np.linalg.lstsq(design, outcome, rcond=None)
    n, k = design.shape
    ids, clusters = pd.factorize(order_ids)
    g = len(clusters)
    if rank < k or g < MIN_CLUSTERS or n <= k:
        return coefficients, None
    residuals = outcome - design @ coefficients
    scores = np.zeros((g, k))
    np.add.at(scores, ids, design * residuals[:, None])
    bread = np.linalg.inv(design.T @ design)
    correction = (g / (g - 1)) * ((n - 1) / (n - k))
    covariance = correction * bread @ (scores.T @ scores) @ bread
    return coefficients, covariance


def _estimate(weights: np.ndarray, fit: tuple[np.ndarray, np.ndarray | None]) -> dict:
    coefficients, covariance = fit
    point = float(weights @ coefficients)
    variance = float(weights @ covariance @ weights) if covariance is not None else 0.0
    if variance <= np.finfo(float).eps:
        return {"estimate": point, "low": None, "high": None, "p_value": None}
    error = sqrt(variance)
    return {
        "estimate": point,
        "low": point - Z_95 * error,
        "high": point + Z_95 * error,
        "p_value": erfc(abs(point) / (sqrt(2) * error)),
    }


def _group_design(frame: pd.DataFrame, group: str) -> tuple[list[str], np.ndarray]:
    indicators = pd.get_dummies(frame[group].astype(str), dtype=float)
    return indicators.columns.tolist(), indicators.to_numpy()


def _fit(frame: pd.DataFrame, design: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
    return _clustered_fit(design, frame.status.eq("succeeded").to_numpy(float), frame.order_id)


def _contrast(
    levels: list[str],
    fit: tuple[np.ndarray, np.ndarray | None],
    terms: dict[str, int],
    counts: pd.Series,
) -> dict | None:
    if set(terms) - set(levels):
        return None
    coefficients, covariance = fit
    if min(counts[level] for level in terms) < MIN_CLUSTERS:
        covariance = None
    weights = np.zeros(len(coefficients))
    for level, weight in terms.items():
        weights[levels.index(level)] = weight
    return _estimate(weights, (coefficients, covariance))


def _period_frame(attempts: pd.DataFrame) -> pd.DataFrame:
    periods = incident_period(attempts.created_at, INCIDENT_START, INCIDENT_END)
    frame = attempts.assign(period=periods).dropna(subset=["period"])
    return frame.assign(cell=frame.provider.astype(str) + " / " + frame.period.astype(str))


def success_intervals(attempts: pd.DataFrame) -> pd.DataFrame:
    """Интервалы для всей выборки и для непустых пар провайдер / окно."""
    complete = attempts.assign(period="Вся выборка", cell=attempts.provider.astype(str))
    total = attempts.assign(period="Вся выборка", provider="Все", cell="Все")
    rows = []
    for frame in (total, complete, _period_frame(attempts)):
        if frame.empty:
            continue
        levels, design = _group_design(frame, "cell")
        fit = _fit(frame, design)
        counts = frame.groupby("cell").order_id.nunique()
        for level, group in frame.groupby("cell", sort=True):
            result = _contrast(levels, fit, {level: 1}, counts)
            low, high = result["low"], result["high"]
            rows.append(
                {
                    "period": group.period.iloc[0],
                    "provider": group.provider.iloc[0],
                    "attempts": len(group),
                    "orders": counts[level],
                    "estimate": result["estimate"],
                    "low": max(0, low) if low is not None else None,
                    "high": min(1, high) if high is not None else None,
                }
            )
    return pd.DataFrame(rows, columns=RATE_COLUMNS)


def _adjusted_design(frame: pd.DataFrame, design: np.ndarray) -> np.ndarray:
    categories = pd.get_dummies(
        frame[["payment_method", "device"]].astype(str), drop_first=True, dtype=float
    )
    amount = np.log(frame.amount_rub.to_numpy(float))
    if np.ptp(amount) > 0:
        categories = categories.assign(log_amount=amount - amount.mean())
    return np.column_stack((design, categories.to_numpy()))


def incident_tests(attempts: pd.DataFrame) -> pd.DataFrame:
    """Двусторонние тесты разницы долей и DiD; контрольный провайдер — alpha."""
    rows = []
    whole = attempts.loc[attempts.provider.isin(["alpha", "beta"])]
    if whole.empty:
        return pd.DataFrame(columns=COMPARISON_COLUMNS)

    levels, design = _group_design(whole, "provider")
    result = _contrast(
        levels,
        _fit(whole, design),
        {"beta": 1, "alpha": -1},
        whole.groupby("provider").order_id.nunique(),
    )
    if result is not None:
        rows.append({"comparison": "beta − alpha, вся выборка", **result})

    previous_start = INCIDENT_START - (INCIDENT_END - INCIDENT_START)
    placebo = incident_period(whole.created_at, previous_start, INCIDENT_START)
    previous = whole.assign(period=placebo).loc[placebo.isin([BEFORE, DURING])]
    previous = previous.assign(
        cell=previous.provider.astype(str) + " / " + previous.period.astype(str)
    )
    frame = _period_frame(whole)
    during = {
        f"beta / {DURING}": 1,
        f"alpha / {DURING}": -1,
        f"beta / {BEFORE}": -1,
        f"alpha / {BEFORE}": 1,
    }
    after = {
        f"beta / {AFTER}": 1,
        f"alpha / {AFTER}": -1,
        f"beta / {BEFORE}": -1,
        f"alpha / {BEFORE}": 1,
    }
    for sample, adjusted, contrasts in (
        (frame, False, [(INCIDENT_DID, during), ("DiD, после сбоя", after)]),
        (previous, False, [("DiD, плацебо до сбоя", during)]),
        (frame, True, [("DiD, во время сбоя с поправкой на состав", during)]),
        (
            frame.loc[frame.attempt_number.eq(1)],
            True,
            [("DiD, только первые попытки с поправкой на состав", during)],
        ),
    ):
        if sample.empty:
            continue
        levels, design = _group_design(sample, "cell")
        if adjusted:
            design = _adjusted_design(sample, design)
            if np.linalg.matrix_rank(design) < design.shape[1]:
                continue
        fit = _fit(sample, design)
        counts = sample.groupby("cell").order_id.nunique()
        for label, terms in contrasts:
            result = _contrast(levels, fit, terms, counts)
            if result is not None:
                rows.append({"comparison": label, **result})

    return pd.DataFrame(rows, columns=COMPARISON_COLUMNS)
