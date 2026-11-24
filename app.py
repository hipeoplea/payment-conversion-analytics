"""Главная страница учебного Streamlit-дашборда."""

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from src.analytics.impact import estimate_impact
from src.analytics.metrics import calculate, order_metrics_by
from src.analytics.segments import (
    attempts_by_segment,
    daily_provider_metrics,
    incident_comparison,
    with_order_context,
)
from src.analytics.statistics import INCIDENT_DID, incident_tests, success_intervals
from src.dashboard.charts import daily_rate_chart, failure_chart, success_rate_chart
from src.data.generator import INCIDENT_END, INCIDENT_START
from src.data.loading import csv_versions, load_data

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
REPORT = PROJECT_DIR / "reports" / "analysis.md"
TABLE_LABELS = {
    "provider": "Провайдер",
    "payment_method": "Способ оплаты",
    "device": "Устройство",
    "attempt_number": "Номер попытки",
    "period": "Период",
    "attempts": "Попытки",
    "successes": "Успешные",
    "successful": "Успешные",
    "technical_failures": "Технические отказы",
    "success_rate": "Доля успешных",
    "technical_failure_rate": "Доля технических отказов",
}


@st.cache_data(show_spinner="Загружаем данные…")
def cached_data(
    data_dir: Path, versions: tuple[tuple[int, int] | None, ...]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    return load_data(data_dir)


def show_percent_table(
    frame: pd.DataFrame, rates: dict[str, str], columns: dict | None = None
) -> None:
    """Передаёт проценты как числа, сохраняя числовую сортировку таблицы."""
    columns = dict(columns or {})
    columns.update(
        {key: st.column_config.NumberColumn(label, format="%.2f%%") for key, label in rates.items()}
    )
    display = frame.assign(**{column: frame[column] * 100 for column in rates})
    st.dataframe(display, column_config=columns, hide_index=True)


def show_attempt_table(frame: pd.DataFrame) -> None:
    rates = {key: TABLE_LABELS[key] for key in ("success_rate", "technical_failure_rate")}
    labels = {key: label for key, label in TABLE_LABELS.items() if key not in rates}
    show_percent_table(frame.rename(columns=labels), rates)


def show_findings(tests: pd.DataFrame, base: pd.Series | None, routes: pd.DataFrame) -> None:
    incident = tests.loc[tests.comparison.eq(INCIDENT_DID)]
    if not incident.empty or base is not None or not routes.empty:
        st.subheader("Главные выводы")
        st.caption("Синтетический сбой beta 12–17 октября 2026 года")
        observed, recovery, pilot = st.columns(3)
        if not incident.empty:
            estimate = incident.iloc[0]
            observed.metric(
                "Изменение beta относительно alpha", f"{estimate.estimate * 100:+.2f} п. п."
            )
            if pd.notna(estimate.low) and pd.notna(estimate.high):
                observed.caption(
                    f"95% ДИ от {estimate.low * 100:.2f} до {estimate.high * 100:.2f} п. п."
                )
        if base is not None:
            recovery.metric("GMV в базовом сценарии", f"+{base.gmv_rub / 1000:.1f} тыс. ₽")
            recovery.caption(
                f"≈ {base.additional_paid_orders:.0f} дополнительных оплат "
                f"и {base.fee_rub / 1000:.1f} тыс. ₽ комиссий"
            )
        if not routes.empty:
            route = routes.iloc[0]
            pilot.metric(
                f"Пилот на alpha · {route.coverage:.0%} трафика",
                f"+{route.additional_paid_orders:.0f} оплат",
            )
            pilot.caption(f"Сценарная оценка · {route.fee_rub:,.0f} ₽ комиссий")
    if REPORT.is_file():
        st.download_button(
            "Скачать аналитический отчёт",
            REPORT.read_bytes(),
            file_name="payment-conversion-analysis.md",
            mime="text/markdown",
        )


def show_overview(orders: pd.DataFrame, attempts: pd.DataFrame) -> None:
    metrics = calculate(orders, attempts)
    st.caption("Показатели рассчитаны по всем заказам и попыткам в наборе данных.")
    total, conversion, gmv, revenue = st.columns(4)
    total.metric("Создано заказов", f"{metrics.orders:,}")
    conversion.metric(
        "Конверсия заказов", f"{metrics.order_conversion:.1%}" if metrics.orders else "—"
    )
    gmv.metric("GMV", f"{metrics.gmv_rub:,.0f} ₽")
    revenue.metric("Комиссии", f"{metrics.fee_revenue_rub:,.0f} ₽")

    count, attempt_success = st.columns(2)
    count.metric("Попытки оплаты", f"{metrics.payment_attempts:,}")
    attempt_success.metric(
        "Успешность всех попыток",
        f"{metrics.attempt_success_rate:.1%}" if metrics.payment_attempts else "—",
    )

    funnel, retries = st.columns(2)
    with funnel:
        st.dataframe(
            pd.DataFrame(
                {
                    "Этап": ["Создан заказ", "Была попытка оплаты", "Заказ оплачен"],
                    "Заказы": [metrics.orders, metrics.orders_with_attempt, metrics.paid_orders],
                }
            ),
            hide_index=True,
        )
    with retries:
        retry_rate = metrics.retry_success_rate
        st.metric(
            "Оплачено среди заказов с повтором",
            f"{retry_rate:.1%}" if retry_rate is not None else "—",
        )
        st.caption(
            f"С первой попытки оплачено {metrics.first_attempt_paid_orders:,} заказов. "
            f"После повтора оплачено {metrics.paid_after_retry:,} из {metrics.retry_orders:,}."
        )

    daily = order_metrics_by(orders, attempts, "date")
    if not daily.empty:
        indicators = {
            "order_conversion": "Конверсия заказов",
            "orders": "Создано заказов",
            "gmv_rub": "GMV, ₽",
            "fee_rub": "Комиссионная выручка, ₽",
        }
        indicator = st.selectbox(
            "По дате создания заказа", list(indicators), format_func=indicators.__getitem__
        )
        chart = px.line(
            daily, x="date", y=indicator, markers=True, labels={"date": "Дата", **indicators}
        )
        chart.update_xaxes(tickformat="%d.%m", hoverformat="%d.%m.%Y")
        if indicator == "order_conversion":
            chart.update_yaxes(tickformat=".0%")
        st.plotly_chart(chart)
        by_device = order_metrics_by(orders, attempts, "device")
        show_percent_table(
            by_device[["device", "orders", "paid_orders", "order_conversion"]].rename(
                columns={"device": "Устройство", "orders": "Заказы", "paid_orders": "Оплачено"}
            ),
            {"order_conversion": "Конверсия заказов"},
        )


def show_diagnostics(attempts: pd.DataFrame) -> None:
    with st.sidebar:
        st.header("Фильтры попыток")
        provider_options = sorted(attempts.provider.unique())
        method_options = sorted(attempts.payment_method.unique())
        device_options = sorted(attempts.device.unique())
        providers = st.multiselect("Провайдер", provider_options, default=provider_options)
        methods = st.multiselect("Способ оплаты", method_options, default=method_options)
        devices = st.multiselect("Устройство", device_options, default=device_options)
    st.caption("Фильтры применяются к попыткам в этом разделе.")
    selected = attempts.loc[
        attempts.provider.isin(providers)
        & attempts.payment_method.isin(methods)
        & attempts.device.isin(devices)
    ]
    if selected.empty:
        st.info("По выбранным условиям попыток оплаты нет")
        return

    st.metric("Успешность выбранных попыток", f"{selected.status.eq('succeeded').mean():.1%}")
    daily = daily_provider_metrics(selected)
    left, right = st.columns(2)
    left.plotly_chart(success_rate_chart(daily))
    right.plotly_chart(
        daily_rate_chart(daily, "technical_failure_rate", "Технические отказы по дням")
    )

    segment = st.selectbox(
        "Разрез",
        ["provider", "payment_method", "device", "attempt_number"],
        format_func=TABLE_LABELS.__getitem__,
    )
    show_attempt_table(attempts_by_segment(selected, segment))
    if selected.status.eq("failed").any():
        st.plotly_chart(failure_chart(selected))
    else:
        st.info("В выбранной группе все попытки успешны.")


def show_incident(attempts: pd.DataFrame, tests: pd.DataFrame, base: pd.Series | None) -> None:
    st.caption("Сбой beta 12–17 октября задан в симуляторе. Сравниваются три шестидневных окна.")
    comparison = incident_comparison(attempts, INCIDENT_START, INCIDENT_END)
    if comparison.empty:
        st.info("В окнах сравнения нет попыток оплаты.")
    else:
        left, right = st.columns(2)
        daily = daily_provider_metrics(attempts)
        dates = pd.to_datetime(daily.date)
        width = INCIDENT_END - INCIDENT_START
        in_scope = daily.loc[dates.ge(INCIDENT_START - width) & dates.lt(INCIDENT_END + width)]
        left.plotly_chart(success_rate_chart(in_scope))
        right.plotly_chart(
            daily_rate_chart(in_scope, "technical_failure_rate", "Технические отказы в окнах сбоя")
        )
        show_attempt_table(comparison)

    intervals = success_intervals(attempts)
    if not intervals.empty:
        st.subheader("Успешность попыток и 95%-е интервалы")
        show_percent_table(
            intervals.rename(columns={**TABLE_LABELS, "orders": "Заказы"}),
            {"estimate": "Доля", "low": "Нижняя", "high": "Верхняя"},
        )
    if not tests.empty:
        st.subheader("Проверка гипотез")
        percent_points = tests.assign(
            **{column: tests[column] * 100 for column in ("estimate", "low", "high")}
        )
        st.dataframe(
            percent_points.rename(columns={"comparison": "Сравнение"}),
            column_config={
                "estimate": st.column_config.NumberColumn("Оценка, п. п.", format="%.2f"),
                "low": st.column_config.NumberColumn("Нижняя, п. п.", format="%.2f"),
                "high": st.column_config.NumberColumn("Верхняя, п. п.", format="%.2f"),
                "p_value": st.column_config.NumberColumn("p-значение", format="%.2e"),
            },
            hide_index=True,
        )
    st.caption(
        "Стандартные ошибки кластеризованы по заказу. DiD сравнивает изменение beta с alpha. "
        "Интервалы не учитывают неопределённость от общих шоков провайдера."
    )

    if base is not None:
        st.subheader("Денежный ориентир базового сценария")
        st.write(
            f"Около {base.additional_paid_orders:.0f} дополнительных оплаченных заказов, "
            f"{base.gmv_rub:,.0f} ₽ GMV и {base.fee_rub:,.0f} ₽ комиссий. "
            "Допущения и варианты переключения приведены в разделе рекомендаций."
        )


def show_recommendations(facts: dict, scenarios: pd.DataFrame, routes: pd.DataFrame) -> None:
    st.subheader("Возможный эффект восстановления")
    st.caption(
        "Сценарии для заказов, чья первая попытка была через beta в окно сбоя. "
        "Доход рассчитан по модельным тарифам и зависит от допущений о составе трафика."
    )
    if scenarios.empty:
        st.info("Недостаточно данных в сопоставимых группах для денежной оценки.")
        return
    cohort, unpaid, support = st.columns(3)
    cohort.metric("Заказов в когорте", facts["cohort_orders"])
    unpaid.metric("Остались неоплаченными", facts["unpaid_orders"])
    support.metric("В сопоставимых группах", facts["supported_orders"])
    values = {
        "additional_paid_orders": st.column_config.NumberColumn("Оплаты", format="%.1f"),
        "gmv_rub": st.column_config.NumberColumn("GMV, ₽", format="%.0f"),
        "fee_rub": st.column_config.NumberColumn("Комиссии, ₽", format="%.0f"),
    }
    show_percent_table(
        scenarios.rename(columns={"scenario": "Сценарий"}),
        {"reference_rate": "Ориентир конверсии"},
        values,
    )

    st.markdown(
        "**1. Настроить мониторинг.** Отслеживать успешность и технические отказы по провайдеру "
        "и способу оплаты с минимальным порогом объёма. "
        "При отклонении сверять логи маршрутизации и статусы провайдера."
    )
    if not routes.empty:
        st.subheader("Пилот переключения на alpha")
        show_percent_table(
            routes,
            {"coverage": "Доля подходящего трафика", "reference_rate": "Ориентир конверсии"},
            values,
        )
        pilot = routes.iloc[0]
        st.markdown(
            f"**2. Проверить переключение на 25% подходящего трафика.** Сценарий оценивает "
            f"около {pilot.additional_paid_orders:.0f} дополнительных оплат "
            f"и {pilot.fee_rub:,.0f} ₽ комиссий за сопоставимое окно. "
            "Проверять эффект по итоговой конверсии заказов, комиссии и времени ответа alpha."
        )
    st.markdown(
        "**3. Проверить вход в оплату.** Разобрать заказы без первой попытки по событиям "
        "открытия платёжной формы и выбора метода."
    )


def main() -> None:
    st.set_page_config(page_title="Аналитика онлайн-платежей", layout="wide")
    st.title("Анализ конверсии онлайн-платежей")
    st.caption("Учебный продуктовый кейс · синтетические данные")

    try:
        orders, attempts = cached_data(DATA_DIR, csv_versions(DATA_DIR))
    except (OSError, ValueError) as exc:
        st.error(f"Ошибка загрузки данных. {exc}")
        return

    enriched = with_order_context(orders, attempts)
    facts, scenarios, routes = estimate_impact(enriched)
    tests = incident_tests(enriched)
    base = scenarios.set_index("scenario").loc["Базовый"] if not scenarios.empty else None
    overview, diagnostics, incident, recommendations = st.tabs(
        [
            "Обзор продукта",
            "Диагностика платежей",
            "Анализ инцидента",
            "Рекомендации",
        ]
    )
    with overview:
        show_findings(tests, base, routes)
        show_overview(orders, attempts)
    with diagnostics:
        show_diagnostics(enriched)
    with incident:
        show_incident(enriched, tests, base)
    with recommendations:
        show_recommendations(facts, scenarios, routes)


if __name__ == "__main__":
    main()
