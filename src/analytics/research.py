"""Повторение расчётов портфолио-исследования из командной строки."""

import argparse
from pathlib import Path

import pandas as pd

from src.analytics.impact import estimate_impact
from src.analytics.metrics import calculate, order_metrics_by
from src.analytics.segments import attempts_by_segment, incident_comparison, with_order_context
from src.analytics.statistics import incident_tests, success_intervals
from src.data.generator import INCIDENT_END, INCIDENT_START
from src.data.loading import load_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Рассчитать показатели и сценарии исследования")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    orders, attempts = load_data(args.data_dir)
    enriched = with_order_context(orders, attempts)
    facts, scenarios, routing = estimate_impact(enriched)

    print("Воронка и оборот", calculate(orders, attempts), sep="\n", end="\n\n")
    for title, table in (
        ("Конверсия заказов по устройству", order_metrics_by(orders, attempts, "device")),
        ("Попытки по провайдерам", attempts_by_segment(enriched, "provider")),
        ("Попытки по способам оплаты", attempts_by_segment(enriched, "payment_method")),
        ("Попытки по устройствам", attempts_by_segment(enriched, "device")),
        ("Причины отказов", attempts.failure_reason.value_counts().reset_index()),
        ("Окна инцидента", incident_comparison(enriched, INCIDENT_START, INCIDENT_END)),
        ("Доверительные интервалы", success_intervals(enriched)),
        ("Проверка гипотез", incident_tests(enriched)),
        ("Когорта денежной оценки", facts),
        ("Сценарии восстановления", scenarios),
        ("Сценарии переключения", routing),
    ):
        output = table.to_string(index=False) if isinstance(table, pd.DataFrame) else table
        print(title, output, sep="\n", end="\n\n")


if __name__ == "__main__":
    main()
