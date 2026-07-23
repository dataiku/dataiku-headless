# Data Quality Rule Types

Read this reference when interpreting an existing rule's `type` or selecting an appropriate rule for a Cobuild request.

| Type | What it checks |
| --- | --- |
| `RecordCountInRangeRule` | Row count within hard or soft bounds |
| `ColumnMinInRangeRule` | Column minimum within hard or soft bounds |
| `ColumnMaxInRangeRule` | Column maximum within hard or soft bounds |
| `ColumnAvgInRangeRule` | Column mean within hard or soft bounds |
| `ColumnMedianInRangeRule` | Column median within hard or soft bounds |
| `ColumnSumInRangeRule` | Column sum within hard or soft bounds |
| `ColumnStdDevInRangeRule` | Column standard deviation within hard or soft bounds |
| `ColumnCountInRangeRule` | Dataset column count within hard or soft bounds |
| `ValuesInRangeRule` | Every individual value in a column is within bounds |
| `numericRange` | A Dataiku metric value is within hard or soft bounds |
| `DriftRecordCountRule` | Record count has not shifted from its historical baseline |
| `DriftColumnCountRule` | Column count has not shifted from its historical baseline |
| `DriftColumnMinRule` / `DriftColumnMaxRule` / `DriftColumnAvgRule` / `DriftColumnMedianRule` / `DriftColumnSumRule` / `DriftColumnStdDevRule` | Corresponding column statistic has not shifted from its historical baseline |
| `DriftColumnEmptyValueCountRule` / `DriftColumnUniqueValueCountRule` | Empty-value or unique-value count has not shifted from its historical baseline |
| `DriftMetricRule` | A metric has not shifted from its historical baseline |
| `ColumnNotEmptyRule` | Column empty rate is below a threshold |
| `ColumnEmptyRule` | Column empty rate is above a threshold |
| `ColumnUniqueValuesRule` | Column values are unique or near-unique |
| `ValuesInSetRule` | All column values are members of an allowed set |
| `TopValuesInSetRule` | The top N most frequent values are all in a specified set |
| `ModeValueInSetRule` | The most frequent value is in a specified set |
| `valueSet` | A Dataiku metric value is one of an allowed set |
| `CompareMetricsRule` | A metric satisfies a comparison against a metric on another dataset |
| `ColumnMeaningValidityRule` | Column values conform to a semantic meaning, such as email or integer |
| `DatasetSchemaEqualsRule` | Dataset schema exactly matches an expected schema |
| `DatasetSchemaContainsRule` | Dataset schema contains specified columns and types |
| `python` | Custom Python check; use only when no built-in rule expresses the required condition |
