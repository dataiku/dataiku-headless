# Web App Insight Reference

Use this reference for `web_app` insight creation and full-settings edits.

## Payload Shape

This reusable insight binds to a DSS webapp.

## Top-Level Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `type` | yes | `string` | Use `web_app`. |
| `name` | yes | `string` | Insight display name. |
| `listed` | no | `boolean` | Public/private insight flag. |
| `dashboardCreationId` | no | `string` | Free-form provenance tag. |
| `params.webAppSmartId` | yes | `string<webapp_id>` | Bound webapp smart id. |
| `params.webAppType` | yes | `string` | `STANDARD` is the common value here. Preserve the live value unless intentionally changing webapp subtype. |

## Dashboard Boundary

- Load-time controls such as `loadTimeoutInSeconds` live at tile level, not in the reusable insight payload.

## Minimal Envelope

```json
{
  "type": "web_app",
  "name": "Loan exploration app",
  "listed": false,
  "params": {
    "webAppSmartId": "B9nqD8z",
    "webAppType": "STANDARD"
  }
}
```
