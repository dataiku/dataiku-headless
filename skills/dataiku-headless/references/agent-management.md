---
name: agent-management
description: Inspect and manage the monitored agent estate through public Agent Management Python SDK methods: platforms, agents, metrics, ingestion operations, risk, settings and tags.
---

# Dataiku Agent Management

Use this guide for the Agent Management product and its monitored agent estate.
Project-level Dataiku agents use [the agents guide](./agents.md) and Cobuild.

## Operation interface

Read [the shared operation guide](./operations.md). Search with
`domain="agent-management"`, describe the selected operation, then use the matching
read/write dispatcher with an `agent-management.` operation ID. The catalog uses
public `dataiku-api-client` methods only and requires version 15.2.0 or newer.
There is no direct endpoint fallback. Catalog presence does not verify a server's
version, permissions or enabled features.

The SDK calls infrastructure records **platforms**. Discover `platform_id` with
`list_platforms`, then `search_agents`; never invent identifiers. Typed
`agent_filter` fields map to public `AgentFilter` builders. Values within one
criterion combine with OR, while different criteria combine with AND. Empty
criterion lists are rejected. Omit the filter for an unfiltered read.

The 46 operations cover platform and agent records/settings, native metric
retrieval, alert evaluation, discovery, monitoring setup, ingestion, operation
status/results/abort, risk assessments and evidence, taxonomy, global settings
and existing tags. Search/describe supplies exact schemas and examples.

## Inspect, change, verify

1. Inspect the selected instance and discover platform and agent IDs.
2. Read the relevant settings, assessment or taxonomy; retain `fetchedRevision`.
3. Describe the write operation and pass that revision as `expected_revision`.
4. Re-read after the write. On conflict, inspect changed state; never retry stale
   intent automatically.

Settings updates use `changes` to replace named **top-level fields** of a freshly
fetched definition. Unnamed fields, including hidden credentials, are retained.
Nested objects and arrays supplied in `changes` are complete replacements: inspect
and preserve their unrelated fields. Do not submit redaction placeholders or put
`fetchedRevision` inside `changes`. Global business KPI definitions are available
through `get_settings` and `update_settings` as `businessKPIs`. Changing definitions
may invalidate stored metrics; `reset_incompatible_metrics=true` explicitly permits
that deletion. The default rejects it.

The `update_settings` example sets `businessKPIs` to an empty list, removing all
business KPI definitions. Use that example only when the user intends to remove
all definitions; otherwise preserve the definitions they want to keep.

Risk-taxonomy replacement requires reviewing
`compute_risk_taxonomy_replacement_impact` for the exact proposed taxonomy, then
passing the returned impact and inspected revision to `update_risk_taxonomy`.
Risk-assessment updates accept an `assessment` object and optional `documents`
mapping evidence IDs to local paths. Evidence download needs `output_path` and
explicit `overwrite=true` to replace an existing destination.

## Monitoring and asynchronous work

Discover qualified metric identifiers with `get_available_metric_ids`; use
`get_metric_time_series` or `get_metric_buckets` with those IDs. Time-series reads
require `from_time` unless `latest_only=true`; latest-only reads forbid time bounds.
Bucketed reads require `from_time`. Time bounds are epoch milliseconds. SDK metric
responses represent timestamps as UTC date/time strings after JSON serialization.

`setup_agent_monitoring` provisions monitoring resources and enables supported
capabilities. Inspect warnings in the returned result; setup does not guarantee
telemetry exists. Discovery, uptime tests and log/operational-metric ingestion
return `platform_id`, optional `agent_id`, and `operation_id`. Keep those identities
on the same instance and poll the corresponding agent/platform status and result
operations. A queued operation is not complete. Aborts are mutations.

`evaluate_alerts` queues evaluation and returns `queued_agent_count`, which counts
agents included in the request, not newly created alerts or completed evaluations.
Review the agent filter first. An absent or empty filter requires
`scope="all_writable_agents"`. The default mode is `DUE`; `FORCE_LATEST` and
`FORCE_CATCH_UP` can invalidate historical alerts and create replacements that do
not inherit acknowledgements. Verify outcomes separately.

## Transport and credentials

Stdio uses configured credentials. HTTP uses the SDK's native delegated bearer
support through `DSSClient.get_agent_management_client()`. Host-file transfers
require stdio; requests with `documents` or `output_path` are rejected after HTTP
token exchange but before SDK execution. Risk-assessment updates without files can
run over HTTP.

Responses recursively redact credentials and sensitive diagnostics. Never share
more business data than needed. Downloaded files use an explicit destination and
atomic no-clobber behavior unless overwrite is requested.
