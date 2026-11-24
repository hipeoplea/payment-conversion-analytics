from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_empty_attempt_filter_keeps_order_metrics():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=15).run()
    assert not app.exception
    assert any(metric.label == "Успешность выбранных попыток" for metric in app.metric)
    assert any(metric.label == "Заказов в когорте" for metric in app.metric)
    overview = app.tabs[0]
    findings = {metric.label: metric.value for metric in overview.get("metric")}
    assert findings["Изменение beta относительно alpha"] == "-22.00 п. п."
    assert findings["GMV в базовом сценарии"] == "+237.7 тыс. ₽"
    assert findings["Пилот на alpha · 25% трафика"] == "+32 оплат"
    assert overview.get("download_button")
    order_metrics = [metric.value for metric in overview.get("metric")]

    app.multiselect[0].set_value([]).run()
    assert not app.exception
    assert app.info[0].value == "По выбранным условиям попыток оплаты нет"
    assert [metric.value for metric in app.tabs[0].get("metric")] == order_metrics
    assert any(metric.label == "Заказов в когорте" for metric in app.metric)
    assert all(metric.label != "Успешность выбранных попыток" for metric in app.metric)


def test_diagnostics_filter_matches_data():
    from src.analytics.segments import with_order_context
    from src.data.loading import load_data

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    orders, attempts = load_data(app_path.parent / "data")
    work = with_order_context(orders, attempts)
    expected = (
        work.loc[
            work.provider.eq("beta") & work.payment_method.eq("card") & work.device.eq("mobile")
        ]
        .status.eq("succeeded")
        .mean()
    )

    app = AppTest.from_file(str(app_path), default_timeout=15).run()
    for widget, value in zip(app.multiselect, ("beta", "card", "mobile"), strict=True):
        widget.set_value([value])
    app.run()

    assert not app.exception
    measure = next(
        metric for metric in app.metric if metric.label == "Успешность выбранных попыток"
    )
    assert measure.value == f"{expected:.1%}"
