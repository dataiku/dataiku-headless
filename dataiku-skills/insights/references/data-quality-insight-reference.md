# Data Quality Insight Reference

Use this reference for `data-quality` insight creation and full-settings edits.

## Payload Shape

This insight binds to a DSS object and shows its data-quality status.

## Top-Level Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `type` | yes | `string` | Use `data-quality`. |
| `name` | yes | `string` | Insight display name. |
| `listed` | no | `boolean` | Public/private insight flag. |
| `dashboardCreationId` | no | `string` | Free-form provenance tag. |
| `params.objectSmartId` | yes | `string<object_id>` | Bound DSS object id. |
| `params.objectType` | yes | `string` | `DATASET` is the common value here. Preserve the live object type. |
| `params.statusType` | yes | `string` | `CURRENT_STATUS` is the common value here. Preserve the live value unless intentionally changing status scope. |

## Minimal Envelope

```json
{
  "type": "data-quality",
  "name": "Data quality status on loans_train",
  "listed": false,
  "params": {
    "objectSmartId": "loans_train",
    "objectType": "DATASET",
    "statusType": "CURRENT_STATUS"
  }
}
```
