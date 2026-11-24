import pandas as pd
import pytest

from src.data.generator import SimulationConfig, generate
from src.data.loading import ATTEMPTS_CSV, ORDERS_CSV, csv_versions, load_data


def test_load_csv_pair_and_reject_incomplete_pair(tmp_path):
    assert csv_versions(tmp_path) == (None, None)
    orders, attempts = generate(SimulationConfig(orders=30, seed=7))
    orders.to_csv(tmp_path / ORDERS_CSV, index=False)
    with pytest.raises(ValueError, match=ATTEMPTS_CSV):
        load_data(tmp_path)

    attempts.to_csv(tmp_path / ATTEMPTS_CSV, index=False)
    versions = csv_versions(tmp_path)
    assert all(version is not None for version in versions)
    loaded_orders, loaded_attempts = load_data(tmp_path)
    pd.testing.assert_frame_equal(loaded_orders, orders, check_dtype=False)
    pd.testing.assert_frame_equal(
        loaded_attempts.astype({"failure_reason": "string"}),
        attempts.astype({"failure_reason": "string"}),
        check_dtype=False,
    )
    (tmp_path / ATTEMPTS_CSV).unlink()
    assert csv_versions(tmp_path) == (versions[0], None)


def test_load_generated_data_when_both_files_are_missing(tmp_path, monkeypatch):
    orders, attempts = generate(SimulationConfig(orders=15))
    monkeypatch.setattr("src.data.loading.generate", lambda: (orders, attempts))
    actual_orders, actual_attempts = load_data(tmp_path)
    pd.testing.assert_frame_equal(actual_orders, orders)
    pd.testing.assert_frame_equal(actual_attempts, attempts)
    assert not list(tmp_path.iterdir())


def test_load_orders_with_no_attempts(tmp_path):
    orders, attempts = generate(SimulationConfig(orders=20, no_attempt_probability=1 - 1e-9))
    orders.to_csv(tmp_path / ORDERS_CSV, index=False)
    attempts.to_csv(tmp_path / ATTEMPTS_CSV, index=False)
    loaded_orders, loaded_attempts = load_data(tmp_path)
    assert len(loaded_orders) == 20
    assert loaded_attempts.empty
