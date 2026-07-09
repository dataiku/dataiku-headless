# Scenario Run Button Insight Reference

Use this reference for `scenario_run_button` insight creation and full-settings edits.

## Payload Shape

This reusable insight binds to a scenario and renders as a runnable control when pinned on dashboards.

## Top-Level Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `type` | yes | `string` | Use `scenario_run_button`. |
| `name` | yes | `string` | Insight display name. |
| `listed` | no | `boolean` | Public/private insight flag. |
| `dashboardCreationId` | no | `string` | Free-form provenance tag. |
| `params.scenarioSmartId` | yes | `string<scenario_id>` | Bound scenario id. |

## Dashboard Boundary

- Button display options such as whether to show the last run live at tile level, not in the reusable insight payload.

## Minimal Envelope

```json
{
  "type": "scenario_run_button",
  "name": "Run flow button",
  "listed": false,
  "params": {
    "scenarioSmartId": "RUN_FLOW"
  }
}
```
