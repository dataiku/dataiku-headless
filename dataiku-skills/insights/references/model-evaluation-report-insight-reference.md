# Model Evaluation Report Insight Reference

Use this reference for `model-evaluation_report` insight creation and full-settings edits.

## Payload Shape

The reusable insight mainly binds to a model evaluation store entry. Dashboard tiles choose which evaluation section to show.

## Top-Level Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `type` | yes | `string` | Use `model-evaluation_report`. |
| `name` | yes | `string` | Insight display name. |
| `listed` | no | `boolean` | Public/private insight flag. |
| `dashboardCreationId` | no | `string` | Free-form provenance tag. |
| `params.mesSmartId` | yes | `string<model_evaluation_store_id>` | Bound model evaluation smart id. |

## Dashboard Boundary

- The reusable insight binds to the evaluation object.
- Dashboard tile options such as `displayMode` belong on the dashboard tile, not the insight payload.

Tile-level `displayMode` values seen on live dashboards included:

- `summary`
- `tabular-input_data_drift`
- `tabular-prediction_drift`
- `tabular-performance_drift`

## Minimal Envelope

```json
{
  "type": "model-evaluation_report",
  "name": "Loan default evaluation report",
  "listed": false,
  "params": {
    "mesSmartId": "z57uSpit"
  }
}
```
