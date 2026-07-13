# Time Series Forecasting

Time series forecasting predicts future values using historical observations along a time axis. Multiple parallel series can be defined through identifier columns.

## Design Guidance

Identify the time column, target column or columns, series identifiers, forecast horizon, and expected scoring cadence.

Validate chronologically. Random train/test splits leak future information into training and make forecast performance appear stronger than it will be in production.

Inspect missing time periods, duplicate timestamps, irregular frequency, seasonality, trend, and structural breaks. These conditions affect both feature design and the interpretation of forecast error.

## Evaluation And Interpretation

Compare forecasts with simple baselines, such as a recent-value or seasonal-naive forecast. A complex model should demonstrate value beyond an appropriate baseline.

Interpret error by horizon. A model can be accurate one period ahead but unreliable at longer horizons.

Assess errors across series, time periods, and target ranges. Aggregate metrics can hide poor performance for important series or peak-demand periods.

## Red Flags

- Validation includes information from after the forecast cutoff.
- The requested horizon is longer than the available history can support.
- Major gaps, duplicates, or frequency changes are unresolved.
- A model is compared only with other complex models, not a simple baseline.
- Important future covariates are unavailable at scoring time.
