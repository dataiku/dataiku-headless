# Causal Prediction

Causal prediction estimates the effect of a treatment variable on an outcome while accounting for confounders. It answers a different question from prediction: what changed because of the treatment, not what is merely associated with the outcome.

## Design Guidance

Identify the treatment, outcome, and pre-treatment confounders explicitly. Include variables that influence both treatment assignment and outcome, but do not include variables caused by the treatment.

The source data must provide meaningful overlap: comparable treated and untreated records should exist across relevant confounder values. A model cannot reliably estimate effects outside the observed support.

Use a time-aware design when treatment and outcome have temporal order. Avoid features recorded after treatment assignment or after the outcome.

## Evaluation And Interpretation

A causal estimate depends on identification assumptions, data quality, and overlap, not only model metrics. Report the estimated effect with its uncertainty and explain the assumptions required for interpretation.

Treat heterogeneous effect estimates cautiously. A subgroup result may be unstable when the subgroup is small or lacks treated/untreated overlap.

## Red Flags

- Treatment occurs after the outcome or has ambiguous timing.
- A feature is measured after treatment assignment.
- Treated and untreated populations have little overlap.
- Important confounders are unavailable.
- The request treats a predictive feature importance as causal evidence.
