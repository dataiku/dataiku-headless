# KNIME node → Dataiku translation

Match nodes on the `factory` class from `settings.xml` (display names are user-editable).
Factory classes below are abbreviated to their last segment minus `NodeFactory`.

## Tabular nodes → recipes

| KNIME node (factory) | Dataiku | Notes |
|---|---|---|
| `CSVTableReader`, `ExcelTableReader`, `FileReader` | Dataset (UploadedFiles) | File is in the archive's `data/` when `file_system_specifier=knime.workflow.data`. Upload, then `set-schema` from the reader's `table_spec_config_Internals` column types (DSS infers all-STRING) |
| `ExcelTableWriter`, `CSVWriter` | Output dataset (+ export recipe if a real file is needed) | The written file in `data/` is your ground truth |
| `KnimeTableReader` (`.table`) | Dataset | Decode per `overview.md` § `.table`, or locate the row(s) in the source CSV via the KNIME row key |
| `DataColumnSpecFilter` (Column Filter) | Prepare `ColumnsSelector` | `included_names` → `columns`, `keep:true` |
| `RowFilter` / `RowFilter2Port` (Row Splitter) | Prepare `FilterOnCustomFormula` / Split recipe | Both-branches-consumed → Split recipe (same rule as Alteryx Filter) |
| `Joiner2` / `Joiner3` | Join | KNIME join modes map to inner/left/right/outer; "unmatched rows to separate port" → Join extra outputs |
| `AppendedRows` (Concatenate) | Stack | |
| `GroupBy` | Group | Aggregation list in `model`; pass `--no-global-count` |
| `Pivoting` | Pivot or restructure-to-skip | Same modality-scan caveat as Alteryx CrossTab |
| `Unpivoting` | Prepare `MultiColumnFold` | Null-rows-dropped caveat applies (see ayx `tools-join-reshape.md`) |
| `RowKey2` (RowID) | Prepare `AddId` or Window RowNumber | |
| `Rename` (Column Rename) | Prepare `ColumnRenamer` | |
| `StringManipulation`, `Formulas` (Column Expressions) | Prepare Formula (GREL) | KNIME `join()`, `substr()`, `regexReplace()` → GREL equivalents; see `../../dku-cli/references/formulas.md` |
| `JEP` (Math Formula) | Prepare Formula (GREL) | `$col$` → GREL `numval("col")` when spaced |
| `RuleEngine` | Prepare `VisualIfRule`/Formula — **but check the consumer first** | After a Predictor = classification threshold, NOT a recipe (see below). Rules are ordered first-match (`$P (Class=1)$>0.3=> "1"`); `TRUE => x` is the default arm |
| `NumberToString2` / `StringToNumber2` | Usually DROP | Type ceremony for KNIME learners/widgets; DSS handles numeric targets and typed variables natively. Keep only when a real string format change is intended |
| `Normalizer3` + `NormalizerApply` | ML task per-feature rescaling | NOT a recipe pair. If normalized data is needed outside ML, one Prepare with explicit formulas |
| `Sorter` | Sort | |
| `DuplicateRowFilter` | Distinct / Window rank | Subset-key caveat same as Alteryx Unique |
| `Partition` (Partitioning) | ML task split policy — or Split recipe outside ML | Before a Learner: `dku ml set-split A M --train-ratio 0.7` (for `fraction: 0.7`). KNIME `Stratified` sampling has no DSS split equivalent — note it; class imbalance handling via DSS weighting if needed |
| `Ungroup` | Prepare `ArrayFold`/`SplitFold` | Collection columns are rare outside loops |
| `Cache` | DROP | Datasets are materialized |

## ML chains → ONE visual ML task

The canonical KNIME training chain collapses to one DSS ML task + deploy:

```
CSV Reader → Number To String → Partitioning → Learner → Predictor → Scorer
                                                  ↓
                                             Model Writer
```
→ `dku ml create-prediction DS target --type BINARY_CLASSIFICATION` → `set-algorithm` →
`set-params` + `set-split` (algorithm params, split ratio) → `train` → `deploy`. The
Scorer's metrics = `dku ml details`. Model Writer = the saved model.
**6 KNIME nodes → 1 ML task.**

| KNIME learner (factory) | DSS algorithm |
|---|---|
| `RandomForestClassificationLearner2` | `RANDOM_FOREST_CLASSIFICATION` — per-setting param mapping + traps (`maxLevels:-1` → depth 30): `semantics.md` § Random Forest |
| `GradientBoostedTrees*` | `GBT_CLASSIFICATION` / `XGBOOST` |
| `LogisticRegression*` | `LOGISTIC_REGRESSION` |
| `Cluster2` (k-Means) | Clustering task, `KMEANS` — k list + rescaling parity: `semantics.md` § k-Means |
| `H2OIsolationForestLearner` | Clustering task, `ISOLATION_FOREST` (or `create-clustering --guess-policy ANOMALY_DETECTION`) — drop ALL `Table to H2O`/`H2O Local Context` plumbing |
| `DLKeras*` (layer nodes + Learner/Executor) | NO visual equivalent — Python recipe with Keras code env; flag for redesign |

Deployment workflows (`Model Reader` + `Predictor` on new data) → ONE
`create-prediction-scoring` / `create-clustering-scoring` recipe against the saved model —
in DSS, train and deploy are zones of one project (or Deployer across projects), not two
workflow files.

## Loops → grids, scenarios, or restructures

| KNIME loop pattern | Dataiku |
|---|---|
| `LoopStartInterval → k-Means → … → LoopEnd2` (parameter sweep) | The parameter list/grid ON the ML algorithm (`kmeans_clustering.k = [3,4,5,6]`). Loop disappears |
| `LoopStartParOpt/LoopEndParOpt` (Parameter Optimization around a threshold rule + scorer) | DSS threshold optimization: the threshold is auto-optimized on a metric at deploy; `dku model set-threshold SM 0.3` to mirror a KNIME-chosen cut-off |
| `LoopStartChunk` (chunked processing) | Usually unnecessary (memory workaround) — DROP and process whole dataset; else partitioned dataset |
| Group Loop over categories | CROSS/equi-join restructure (same as Alteryx BatchMacro) |
| Recursive Loop | SQL recursive CTE / scenario-loop plugin / Python (same ladder as Alteryx IterativeMacro) |

## Orchestration & app surface

| KNIME node | Dataiku |
|---|---|
| `IntegerDialog`/`StringDialog`… (Configuration nodes) | `dku project set-variables --set k=v`; Dataiku App for an interactive surface |
| `TableToVariable3`, `AppendVariableToTable4`, `VariableToTable4` | DROP (flow-variable plumbing); scenario variables when orchestration-level |
| `CaseStartAny`/`CaseStartVariable` + `SendMail` | Scenario: build step + Python step setting a scenario variable + `dku scenario add-reporter SCEN --recipient … --condition 'outcome == "SUCCESS" && parseInt(variables["n_alerts"]) > 0'` (raw expressions pass through; bare-word typos still error) |
| `Timerinfo` + downstream Math Formula | DROP — DSS job metrics |
| `ReportingDataSet` (Data to Report), BIRT `.rptdesign`, `TextOutputWidget` | Dashboard + insights |
| `Python2Script2` (Python Script) | Python recipe — `input_table_1`→`dataiku.Dataset(...).get_dataframe()`, `output_table_1`→`write_with_schema` |
| `Scorer` (JavaScript) standalone (not post-Predictor) | Group/window + formulas for confusion counts, or model evaluation store |

Collapse triggers for the Phase-2 collapse pass live in `overview.md` § Collapse triggers
& non-migratable patterns (the location `../references/workflow.md` points every source at).
