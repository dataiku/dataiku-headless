---
name: prepare-enrich-with-build-context-processor
description: "Observed JSON patterns for the EnrichWithBuildContextProcessor prepare/shaker processor."
---

# EnrichWithBuildContextProcessor

Adds build-time context columns: build date and build job id. Values meaningful only at build time; design preview shows placeholder job id and wall-clock build date.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `buildDateColumn` | no | `string<column_name>` | Any valid output column name | Build-date column; created only when non-blank; DSS engine=job activity start time; SQL engine=`DATE` from build timestamp. |
| `jobIdColumn` | no | `string<column_name>` | Any valid output column name | Job-id column; created only when non-blank; build job id. Design preview value=placeholder `This column will only be valued at build time`. |

## Canonical Variant

```json
{
  "type": "EnrichWithBuildContextProcessor",
  "params": {
    "buildDateColumn": "build_date",
    "jobIdColumn": "build_job_id"
  }
}
```
