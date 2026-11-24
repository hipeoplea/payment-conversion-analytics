import pandas as pd
import pytest

from src.data.generator import SimulationConfig, generate
from src.data.validation import validate


def test_reproducibility():
    a, b = generate(SimulationConfig(orders=200, seed=13))
    a2, b2 = generate(SimulationConfig(orders=200, seed=13))
    pd.testing.assert_frame_equal(a, a2)
    pd.testing.assert_frame_equal(b, b2)


def test_references_and_lifecycle():
    orders, attempts = generate(SimulationConfig(orders=500, seed=3))
    validate(orders, attempts)
    assert len(orders) == 500
    assert attempts.order_id.isin(orders.order_id).all()


def test_no_attempt_orders():
    orders, attempts = generate(SimulationConfig(orders=100, no_attempt_probability=1 - 1e-9))
    assert len(orders) == 100
    assert attempts.empty
    validate(orders, attempts)


def test_invalid_config():
    with pytest.raises(ValueError):
        SimulationConfig(orders=0)


@pytest.mark.filterwarnings("error::DeprecationWarning")
def test_attempt_offsets_have_explicit_time_unit():
    orders, attempts = generate(SimulationConfig(orders=200, seed=13, no_attempt_probability=0))
    created_by_order = orders.set_index("order_id")["created_at"]
    actual = attempts.created_at - attempts.order_id.map(created_by_order)
    expected = pd.to_timedelta(attempts.attempt_number * 2, unit="min")
    pd.testing.assert_series_equal(actual, expected, check_names=False, check_dtype=False)
