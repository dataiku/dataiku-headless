# Prediction

Prediction analyses learn a target from feature columns. Classification predicts a category; regression predicts a numeric value.

## Design Guidance

Choose the target based on the decision the model must support. Reject identifiers, row numbers, target proxies, and features unavailable at scoring time.

Use a validation split that represents future scoring conditions. Stratify classification splits when class imbalance would otherwise make a minority class underrepresented.

Class imbalance requires metrics and decisions that reflect the minority class. Accuracy can be misleading when one class dominates; use precision, recall, F1, PR AUC, or ROC AUC according to the cost of false positives and false negatives.

## Evaluation And Interpretation

For classification, AUC measures ranking quality across thresholds, not whether the chosen operating threshold meets business needs. Ask which error is more costly before recommending a threshold.

For regression, interpret RMSE or MAE against the target's typical range. An error value is not meaningful without its business scale.

Feature importance describes predictive association, not causation. Investigate a feature with unusually dominant importance, especially if it may be a target proxy or unavailable at scoring time.

## Red Flags

- Accuracy is high but the minority-class recall is poor.
- A feature appears to encode the target or a post-outcome event.
- Train performance is much stronger than validation performance.
- Performance is nearly perfect on a non-trivial problem.
- The dataset has too few rows to support reliable validation.
