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

## Workflow

1. Call `get_mira_api_capabilities` for the relevant domain. Never guess a path
   or probe speculative endpoints.
2. Discover infrastructure and agent IDs through `list_infras` and
   `list_mira_agents` rather than inventing identifiers.
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
