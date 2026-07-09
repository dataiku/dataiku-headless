# Scenario Last Runs Insight Reference

Use this reference for `scenario_last_runs` insight creation and full-settings edits.

## Payload Shape

This reusable insight binds to a scenario. Dashboard tiles can choose simplified or ranged renderings.

## Top-Level Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `type` | yes | `string` | Use `scenario_last_runs`. |
| `name` | yes | `string` | Insight display name. |
| `listed` | no | `boolean` | Public/private insight flag. |
| `dashboardCreationId` | no | `string` | Free-form provenance tag. |
| `params.scenarioSmartId` | yes | `string<scenario_id>` | Bound scenario id. |

## Dashboard Boundary

- Range and simplified timeline rendering live at tile level, not in the reusable insight payload.

## Minimal Envelope

```json
{
  "type": "scenario_last_runs",
  "name": "Scenario last runs",
  "listed": false,
  "params": {
    "scenarioSmartId": "RUN_FLOW"
  }
}
```
