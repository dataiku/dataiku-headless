# KNIME semantics — why values differ

Read when a migrated value disagrees with the KNIME ground truth.

## k-Means is init-sensitive — exact parity is impossible by design

KNIME `k-Means` defaults: `centroid_initialization: FIRST_ROWS` (deterministic — first k
rows are the seeds) and `maxNrIterations: 10` (often stops BEFORE convergence). DSS uses
sklearn k-means++ with full convergence. On the same data both produce valid but different
local optima: cluster sizes and centroids will differ, usually with one or two segments
clearly recognizable across both (verified on the churn sample: the "low day usage"
segment matched 1197 vs 1206 rows; the other two split differently).

Verify segment-level interpretation (count of clusters, ordering of centroid means,
business meaning), NOT row-level assignments. If the user needs exact KNIME assignments,
that's a Python recipe with `init=` first-k-rows and `max_iter=10` — say so explicitly.

KNIME also runs k-Means on raw values unless a `Normalizer` precedes it. DSS clustering
defaults to AVGSTD rescaling — set `dku ml set-feature A M <col> --rescaling NONE` per
feature for parity when KNIME had no Normalizer. The k list itself:
`dku ml set-params A M -a KMEANS --set k=3,4,5,6`.

## Random Forest

Set via `dku ml set-params A M -a RANDOM_FOREST_CLASSIFICATION --set …` and
`dku ml set-split A M --train-ratio 0.7` (the CLI handles DSS's grid-dict /
plain-array payload shapes; see `../../dku-cli/references/mlops.md` if editing raw
settings through `dataikuapi`).

| KNIME RF Learner setting | DSS equivalent | Trap |
|---|---|---|
| `nrModels: 100` | `--set n_estimators=100` | |
| `maxLevels: -1` (unlimited) | `--set max_tree_depth=30` | DSS visual RF requires depth ≥ 1 — no "unlimited"; 30 ≈ unlimited in practice |
| `SquareRoot` column sampling | `--set selection_mode=sqrt` | |
| `fraction: 0.7` on Partitioning | `dku ml set-split --train-ratio 0.7` | |
| `InformationGainRatio` split | not exposed | sklearn uses gini/entropy; metric-level parity only |
| `missingValueHandling: XGBoost` | DSS imputes per feature | Different mechanism; immaterial on complete data |

Expect metric-level parity (AUC/precision/recall within a point), not per-row identical
predictions. Fraud sample: DSS RF reached AUC 0.977, P 0.94 / R 0.93 on the 30 % holdout —
in family with the KNIME original.

## Partitioning

KNIME `Partitioning` with `samplingMethod: Stratified` + seed stratifies on the class
column. DSS `SPLIT_SINGLE_DATASET` random split has **no stratified option** — on highly
imbalanced data (fraud: 0.17 % positives) the holdout positive count can drift slightly.
Acceptable for metric parity; for strict reproduction pre-split with a deterministic
formula (hash of row id) into explicit train/test datasets and use "explicit extracts"
policy.

## Rule Engine

- Rules are ORDERED, first match wins; `TRUE => x` is the default arm.
- `$P (Class=1)$ > 0.3 => "1"` after a Predictor is a classification cut-off →
  `dku model set-threshold SAVED_MODEL 0.3 -P PROJ` (note: DSS auto-optimizes the
  threshold on deploy — e.g. to 0.1 on the fraud sample — so an unset threshold does
  NOT mean 0.5).
- Rule Engine OUTPUTS STRINGS (hence the `String To Number` that often follows). In DSS
  the formula/threshold produces typed output; drop the cast.

## Flow variables & Configuration nodes

- `settings.xml` `config[flow_stack]` holds the values variables HAD at save time; the
  `model` block holds dialog defaults. The executed run's effective parameter = flow_stack
  (or the workflow-configuration in `.artifacts/`). The churn sample's Interval Loop dialog
  said 3→6 but Integer Configurations defaulted min=max=3 — the shipped ground truth
  contains only k=3. **When dialog and output disagree, trust the output** (same authority
  rule as Alteryx cached BrowseV2).
- Configuration node `parameterName` ≠ `flowVariableName` necessarily — use
  `flowVariableName` when mapping to project variable names.

## Dates, types, misc

- KNIME column types in reader specs are Java classes (`java.lang.Double`, `…IntCell`).
  Excel/CSV upload to DSS infers all-STRING — always `set-schema` from the KNIME spec.
- KNIME row keys (`Row0`, `Row83937`) are 0-based source row indices for un-shuffled
  reads — usable to locate ground-truth rows in the original file.
- `state=EXECUTED` in workflow.knime means `data/` outputs are real run artifacts.
- Send Email nodes frequently ship with empty `smtpHost` (instance-level concern in KNIME
  too) — wire the DSS scenario reporter and note that SMTP channel config is an admin step,
  not a migration step.
