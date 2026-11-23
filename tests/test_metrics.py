import pandas as pd
from src.generate_data import generate
from src.metrics import summary, by_segment, daily

def test_reproducible():
    pd.testing.assert_frame_equal(generate(100, 42), generate(100, 42))

def test_invariants():
    df = generate(5000, 7)
    assert len(df) == 5000
    assert df.attempt_id.is_unique
    assert (df.amount_rub > 0).all()
    assert (df.loc[df.status == "failed", "fee_rub"] == 0).all()
    assert df.loc[df.status == "succeeded", "failure_reason"].isna().all()

def test_summary_and_segments():
    df = generate(1000)
    m = summary(df)
    assert m["attempts"] == 1000
    assert 0 < m["payment_success_rate"] < 1
    assert by_segment(df, "provider")["attempts"].sum() == 1000
    assert daily(df)["attempts"].sum() == 1000

def test_no_failures():
    df = generate(10)
    df["status"] = "succeeded"
    df["failure_reason"] = None
    df["fee_rub"] = 1.0
    assert summary(df)["payment_success_rate"] == 1.0
