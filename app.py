"""Interactive payment analytics demo (entirely synthetic)."""
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from src.generate_data import generate
from src.metrics import summary, by_segment, daily

st.set_page_config(page_title="Payment Conversion Analytics", layout="wide")
st.title("Payment Conversion Analytics")
st.warning("DEMO — SYNTHETIC DATA. Patterns and incidents are intentionally simulated.")

@st.cache_data
def load_data() -> pd.DataFrame:
    path = Path("data/payment_attempts.csv")
    if path.exists():
        return pd.read_csv(path, parse_dates=["created_at"])
    return generate()

data = load_data()
with st.sidebar:
    st.header("Filters")
    methods = st.multiselect("Payment methods", sorted(data.payment_method.unique()), default=sorted(data.payment_method.unique()))
    providers = st.multiselect("Providers", sorted(data.provider.unique()), default=sorted(data.provider.unique()))
    devices = st.multiselect("Devices", sorted(data.device.unique()), default=sorted(data.device.unique()))
df = data.loc[data.payment_method.isin(methods) & data.provider.isin(providers) & data.device.isin(devices)]
if df.empty:
    st.info("No attempts match these filters.")
    st.stop()
metrics = summary(df)
a, b, c, d = st.columns(4)
a.metric("Attempts", f"{metrics['attempts']:,}")
b.metric("Payment success rate", f"{metrics['payment_success_rate']:.1%}")
c.metric("Successful GMV", f"₽{metrics['gmv_rub']:,.0f}")
d.metric("Fee revenue", f"₽{metrics['fee_revenue_rub']:,.0f}")
st.caption("Failed requested amount is NOT equivalent to recoverable GMV or lost revenue.")
st.subheader("Success rate over time")
chart = daily(df)
st.plotly_chart(px.line(chart, x="date", y="success_rate", markers=True, labels={"success_rate":"Success rate", "date":"Date"}), use_container_width=True)
left, right = st.columns(2)
with left:
    st.subheader("Success rate by provider")
    p = by_segment(df, "provider")
    st.plotly_chart(px.bar(p, x="provider", y="success_rate", hover_data=["attempts"]), use_container_width=True)
with right:
    st.subheader("Failure reasons")
    failures = df.loc[df.status.eq("failed"), "failure_reason"].value_counts().rename_axis("reason").reset_index(name="attempts")
    st.plotly_chart(px.bar(failures, x="reason", y="attempts"), use_container_width=True)
st.subheader("Segment diagnostics")
dimension = st.selectbox("Segment", ["payment_method", "provider", "device", "merchant_id"])
st.dataframe(by_segment(df, dimension), use_container_width=True, hide_index=True)
st.info("Scenario encoded in generator: provider beta has extra technical failures Oct 12–17, 2026. This is not a discovered real-world incident.")
