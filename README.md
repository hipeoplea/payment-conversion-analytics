# Payment Conversion Analytics

**Portfolio case for product analytics in payment processing.** All payment attempts are **synthetic**, generated deterministically. This project does not use real customers, banking records or proprietary LAVA data.

## Business problem

Which segments have low payment authorization success, when do technical failures spike, and how much requested payment volume is affected? The demo intentionally injects a six-day degradation for provider `beta`; finding it is a sanity check, **not** a real-world discovery.

## Stack

Python, pandas, NumPy, PostgreSQL SQL, Plotly, Streamlit, pytest.

## Quick start

Requires Python 3.10+.

```bash
git clone https://github.com/hipeoplea/payment-conversion-analytics.git
cd payment-conversion-analytics
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m src.generate_data --rows 100000 --seed 42
python -m pytest -q
streamlit run app.py
```

On Windows, activate with `.venv\Scripts\activate`.

You can start the Streamlit app without generating the CSV; it will create an identical deterministic in-memory sample. The CSV is intentionally gitignored.

## Data dictionary

One row = **one payment attempt**, not necessarily a unique order or customer.

| Column | Meaning |
| --- | --- |
| attempt_id | Unique attempt identifier |
| created_at | Attempt timestamp |
| merchant_id / customer_id | Synthetic merchant/customer IDs |
| provider | Payment processing provider (alpha/beta) |
| payment_method | card, sbp, wallet |
| device | mobile, desktop |
| amount_rub | Requested RUB amount |
| status | succeeded or failed |
| failure_reason | Reason on failed attempts only |
| fee_rub | Simulated fee earned only on success |

No checkout sessions, orders, processor cost, refunds or retry links are currently modeled. Hence **checkout conversion, net revenue, true lost sales and recoverable GMV cannot be inferred** from this dataset.

## Metric definitions

- **Payment success rate** = succeeded attempts / all attempts.
- **GMV** = sum of requested amounts **only for succeeded attempts**.
- **Fee revenue** = sum of simulated fees on succeeded attempts; this is *gross fee revenue*, not profit.
- **Failed requested amount** = requested volume associated with failed attempts; **not** lost revenue or recoverable GMV.
- **Technical-failure-at-risk amount** = requested volume for attempts whose failure reason is `technical_error`; no assumption of full recoverability.

See `sql/analysis.sql` for PostgreSQL-compatible analytical queries and DDL.

### PostgreSQL import (optional)

Create the table by running the DDL in `sql/analysis.sql`, then use `psql`:

```sql
\copy payment_attempts(attempt_id,created_at,merchant_id,customer_id,provider,payment_method,device,amount_rub,status,failure_reason,fee_rub) FROM 'data/payment_attempts.csv' CSV HEADER NULL ''
```

Then execute the SELECT statements from `sql/analysis.sql`. Run from the repository root in `psql` (not a generic SQL GUI, where `\copy` is unsupported).

## Synthetic data design

The generator uses NumPy RNG with default seed 42 and produces 100,000 payment attempts across 80 merchants and 20,000 potential customer IDs, over Sep–Oct 2026. It uses arbitrary but documented baseline failure probabilities, with differences by method and mobile device. Additional technical failures are **deliberately injected** for provider `beta` from Oct 12 inclusive to Oct 18 exclusive. These parameters are illustrative, not calibrated estimates of any provider's actual performance.

The project is a **diagnostic analytics demo**, not a validated forecast or causal A/B experiment. An A/B test would require actual randomized assignment, treatment/control identifiers and predeclared hypotheses; these are not yet part of the dataset.

## Next improvements

1. Model checkout sessions, orders, retry attempts and deduplicate outcomes to estimate **checkout-to-paid conversion**.
2. Analyze incident impact with matched control segments and uncertainty intervals.
3. Add a properly randomized synthetic A/B experiment with statistical power and guardrails.
4. Build concise business recommendations with clearly marked assumptions.
5. Add CI and dashboard screenshots once validated.

## Integrity

No real merchant data is included. A failed transaction may be retried later; summing failed amounts overstates actual lost GMV. Treat all monetary outputs as hypothetical.
