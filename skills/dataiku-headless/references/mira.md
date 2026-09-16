---
name: dataiku-mira
description: Inspect and manage the Dataiku Agent Management estate through its complete public API, including infrastructures, monitored agents, metrics, briefings, ingestion operations, risk, settings, KPIs, topic families, and tags.
---

# Dataiku Agent Management (MIRA)

Use this guide for the Agent Management product and its monitored agent estate.
Do not confuse MIRA agents with project-level Dataiku agents covered by
`./agents.md`.

## Tools

- `get_mira_api_capabilities` returns the fixed public API catalog. Filter it by
  `infrastructures`, `agents`, `operations`, `risk`, `settings`, or `tags` when
  only one area is relevant.
- `call_mira_api` executes a catalog operation by `operation_id`. It does not
  accept arbitrary paths or HTTP methods.

The catalog covers every published MIRA controller operation, including reads,
configuration writes, scans, uptime tests, log and metric ingestion, operation
polling and aborts, risk-evidence upload/download, briefing generation, KPI and
topic-family administration, and tags.

## Monitoring thresholds and native alerts

`get_mira_agent_monitoring_thresholds` and
`update_mira_agent_monitoring_thresholds` require a DIP build containing the
public `/dam/infras/{infra_id}/agents/{agent_id}/monitoring-thresholds`
extension. They are not available on every Agent Management release. The catalog
describes client support, not server capability detection. If the instance
returns 404, report the missing backend extension; do not try browser-session
endpoints or silently send thresholds through generic agent settings (which do
not expose this map).

1. Read the threshold context. It returns `revision`, the built-in `metrics`
   catalog, `configuredThresholds`, `effectiveThresholds`, and
   `inheritedThresholds`. Business KPI entries use `business.<kpi_id>` keys in
   the maps; discover their definitions in agent settings. Do not invent metric
   IDs. Not every configurable metric supports time-bucketed alert occurrences.
2. Send a partial update with the **threshold context's revision** (not the
   generic agent-settings revision) as `expectedRevision`, a `thresholds` map,
   and optionally `resetMetricIds`. Only named entries change; omitted metrics
   and unrelated agent configuration are preserved.
3. Re-read the context and inspect effective values and their `source`.
   A 409 means the threshold context changed, including relevant inherited
   rules: re-read and review the change instead of retrying automatically.

Each threshold has `softThreshold` (warning), `hardThreshold` (critical),
`direction` (`AT_OR_ABOVE` or `AT_OR_BELOW`), and `useInherited`.

- Custom rule: set one or both numeric thresholds, direction, and
  `useInherited: false`. Zero is a valid threshold, not a missing value.
- Disable a local rule: set both numeric values to `null` and
  `useInherited: false`. This masks inherited thresholds.
- Inherit while keeping custom values: set `useInherited: true` for built-in
  metrics. Business KPI overrides do not accept this mode.
- Remove a local override: put its ID in `resetMetricIds`; it resumes parent
  resolution (or the business KPI definition). Do not also edit that ID.

Native permission checks, validation, agent history, monitoring status refresh,
and alert-rule reconciliation apply. Configuring monitoring can change a
discovered agent to managed, just as in the UI. This does not provision missing
telemetry or guarantee a new alert immediately.

`evaluate_mira_alerts` calls the public native evaluator with an explicit agent
filter, using the same filter shape as `search_mira_agents`. Review the selected
agents first: an empty filter evaluates every writable agent. Evaluation can
open/close occurrences and append native alert history; it is a mutation, not
a read or dry run. It uses eligible completed time buckets, not fabricated
measurements. Its `evaluatedAgentCount` counts evaluated agents, **not** new
alerts. Verify the resulting conditions/occurrences separately.

## Workflow

1. Call `get_mira_api_capabilities` for the relevant domain. Never guess a path
   or probe speculative endpoints.
2. Discover infrastructure and agent IDs through `list_infras` and
   `search_mira_agents` (use an empty JSON body for an unfiltered search) rather
   than inventing identifiers.
3. Read the current status, settings, metrics, assessment, or taxonomy before
   proposing a change. Preserve the returned revision for optimistic writes.
4. Use `call_mira_api` with the exact `operation_id`, required `path_params`,
   allowed `query_params`, and documented payload kind.
5. For a long-running action, retain the returned operation ID and use the
   matching status and result operations. Do not infer success from launch.
6. After a write, re-read the affected resource and confirm the intended state.

## Payload Rules

- Normal creates and updates use `body` with the complete JSON payload expected
  by the public API.
- `update_agent_risk_assessment` is multipart. Put the serialized assessment and
  current revision in `form_params`. When uploading documents, provide matching
  `documentEvidenceIds` and `file_paths` in the same order.
- `download_agent_risk_evidence` requires `output_path`; it will not overwrite an
  existing file unless `overwrite` is true.
- Query parameter names are case-sensitive and are listed in the capability
  response.

## Safety and Consistency

- Treat configuration changes, scans, ingestion, generated briefings, sign-off,
  aborts, and deletions as mutations. Let the harness obtain user confirmation
  before calling them.
- Settings, infrastructure settings, agent settings, risk assessments, and risk
  taxonomy use revision-aware updates. On conflict, re-read and present the new
  state instead of silently retrying with stale intent.
- Review risk-taxonomy replacement impact before updating the taxonomy.
- Use forced infrastructure deletion only when the user explicitly intends to
  remove managed agents with it.
- Keep downloaded or uploaded evidence local paths explicit. Never expose API
  keys, credentials, or connection secrets in payloads or responses.
