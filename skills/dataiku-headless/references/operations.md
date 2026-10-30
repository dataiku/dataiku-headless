---
name: operations
description: Discover and execute Deployer, Govern and Agent Management operations with typed arguments, node policy and transport checks.
---

# Shared operation interface

Deployer profiles use four fixed MCP tools: search_operations,
describe_operation, run_read_operation and run_write_operation. Product actions
are operation IDs, not individually registered MCP tools. The catalog stays stable
across instance switches. Other profile types cannot use these tools.

## Workflow

1. Select the intended profile using list_instances, get_current_instance and
   switch_instance. A configured node type is policy, not live feature detection.
2. Search by query, domain (deployer), and effect.
   Search filters by selected type. Results default to 10 (maximum 50); use the
   returned next_offset to page with offset, or narrow the query. All four v2
   tools require a selected profile; search and describe inspect the local catalog
   without contacting Dataiku.
3. Describe a returned operation_id. Inspect input_schema, category, effects,
   allowed types, requirements, transports, local_file_fields and response_contract.
   Definitions and settings vary by backend release, infrastructure or blueprint;
   nested objects explicitly described as backend-defined are not fully specified
   by the structural schema. Read their current definitions before replacing them.
Never submit redacted placeholders from a read as replacement values; the write
dispatcher rejects them. Prefer a scoped update that preserves hidden fields, or
report the coverage gap.

4. Discover IDs through reads, then execute with the matching read/write tool and
   an arguments object. Example IDs are structural placeholders, not live defaults.
   Supply expected_instance with the selected instance name to reject stale context.
5. Inspect the returned result and re-read after mutation. Retain operation/future
   IDs and revisions for recovery. Never resubmit an uncertain write automatically.

Middleware checks the tool’s allowed instance types before exchanging credentials.
Execution handlers check operation IDs, node type, effects, argument shape, selected
instance and transport before calling the SDK. A read tool cannot
execute a mutation. Backend permissions remain authoritative. server_support is
unknown until actual read-only evidence establishes availability; do not infer a
missing feature from a single 404 or probe with writes.

## Coverage and transport

- [Deployer](./deployer.md): 13 public SDK operations for Project/API Deployer,
  including deployment future polling. Select a Deployer profile even when it
  shares a URL with a Design or Automation node. Supports stdio and HTTP.

Adapters use public Python SDK methods only. Do not fall back to direct endpoint
calls or another identity when coverage is missing. Project construction remains
with Cobuild on supported Design profiles. No dynamic tool registration or code sandbox is used.
