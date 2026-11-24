"""Графики для анализа попыток оплаты."""

import pandas as pd
import plotly.express as px

RATE_LABELS = {
    "success_rate": "Доля успешных попыток",
    "technical_failure_rate": "Доля технических отказов",
}


def success_rate_chart(daily_metrics: pd.DataFrame):
    return daily_rate_chart(daily_metrics, "success_rate", "Успешность попыток по дням")


def daily_rate_chart(daily_metrics: pd.DataFrame, rate: str, title: str):
    figure = px.line(
        daily_metrics,
        x="date",
        y=rate,
        color="provider",
        markers=True,
        hover_data={"attempts": True, rate: ":.1%"},
        labels={
            "date": "Дата попытки",
            rate: RATE_LABELS[rate],
            "provider": "Провайдер",
            "attempts": "Число попыток",
        },
        title=title,
    )
    figure.update_xaxes(tickformat="%d.%m", hoverformat="%d.%m.%Y")
    figure.update_yaxes(tickformat=".0%")
    return figure


def failure_chart(attempts: pd.DataFrame):
    counts = (
        attempts.loc[attempts.status.eq("failed"), "failure_reason"]
        .value_counts()
        .rename_axis("reason")
        .reset_index(name="attempts")
    )
    return px.bar(
        counts,
        x="reason",
        y="attempts",
        labels={"reason": "Причина отказа", "attempts": "Число попыток"},
        title="Причины неуспешных попыток",
    )
