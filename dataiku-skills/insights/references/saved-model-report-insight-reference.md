# Saved Model Report Insight Reference

Use this reference for `saved-model_report` insight creation and full-settings edits.

## Payload Shape

The reusable insight mainly binds to a saved model. Dashboard tiles choose which report section to show.

## Top-Level Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `type` | yes | `string` | Use `saved-model_report`. |
| `name` | yes | `string` | Insight display name. |
| `listed` | no | `boolean` | Public/private insight flag. |
| `dashboardCreationId` | no | `string` | Free-form provenance tag. |
| `params.savedModelSmartId` | yes | `string<saved_model_smart_id>` | Bound saved model id. |

## Dashboard Boundary

- The reusable insight binds to the model.
- Dashboard tile options such as `displayMode` belong on the dashboard tile, not the insight payload.

Tile-level `displayMode` values seen on live dashboards included:

- `summary`
- `interactive_scoring`
- `feature_importance`
- `coefficients`
- `subpopulation`
- `individual_explanations`
- `bc_confusion`
- `bc_decision_chart`
- `bc_lift`
- `c_calibration`
- `c_roc`
- `c_precision_recall`
- `performance-metrics`

## Minimal Envelope

```json
{
  "type": "saved-model_report",
  "name": "Loan default model report",
  "listed": false,
  "params": {
    "savedModelSmartId": "bd9je77w"
  }
}
```
