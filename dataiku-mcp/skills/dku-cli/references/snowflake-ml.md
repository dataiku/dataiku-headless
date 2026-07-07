# Reference: Snowflake ML from DSS

Driving Snowflake ML functions (`SNOWFLAKE.ML.ANOMALY_DETECTION`,
`SNOWFLAKE.ML.FORECAST`) from DSS SQL.

- **Transactions:** `CREATE SNOWFLAKE.ML.*` fails under DSS's `autocommit=false`
  ("scoped transaction ... rolled back"). Escape hatch: run the CREATE through the
  `snow` CLI (autocommit on), or temporarily flip the connection's autocommit.
- **Detect window:** `DETECT_ANOMALIES` requires evaluation timestamps strictly
  AFTER the last timestamp in the fitting data (it forecasts, then compares). Keep
  ramp-up periods out of training, or the prediction interval inflates and real
  spikes land inside the band.
- **Inputs / persisting results:** pass inputs as `INPUT_DATA => TABLE(view)`;
  persist call output via `RESULT_SCAN(LAST_QUERY_ID())` into a table.
- **Casing:** tables created by the `snow` CLI store unquoted identifiers
  UPPERCASE — lowercase-quoted queries silently return empty. Quoting/casing rules:
  `playbooks/tabular-flow.md` § SQL recipe.
