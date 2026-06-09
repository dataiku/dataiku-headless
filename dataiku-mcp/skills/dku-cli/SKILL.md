---
name: dku-cli
description: Operate Dataiku DSS end to end with the `dku` CLI. Use when deciding which DSS-native capability to use and when executing project, dataset, recipe, job, scenario, dashboard, agent, plugin, webapp, Govern, or admin workflows.
metadata:
  author: dataiku
  tags: dataiku, dss, cli
---

# Dataiku DSS

Use `dku` for both capability choice and execution. Read **one playbook** for your task,
get exact flags from `--help`, open a reference only for JSON payload shapes.

## Exact flags live in `--help`, not in docs

Under this environment `--help` returns machine-readable JSON:

- `dku --help` → groups + root commands + global options
- `dku recipe --help` → terse one-line signature per command in the group
- `dku recipe create-join --help` → full args, flags, types, defaults for one command

Never guess flags and never document them here — drill into command `--help`.

## Permanent rules

1. **Prefer DSS-native features over custom code.** Capability ladder: visual recipe →
   GenAI recipe → AutoML/visual ML → agents & knowledge banks → scenario → SQL recipe →
   Python/R recipe (last resort). Pick the highest rung that fits.
2. **Inspect before you mutate.** `dku project inspect` for substantive work; skip for narrow reads.
3. **Sample and schema-check inputs** before transforming.
4. **Build with** `dku job run --type RECURSIVE_BUILD --auto-update-schema --wait`.
5. **Verify with real data.** Exit 0 is not proof; empty arrays are data, not success. Check row counts, schema, and sample values.
6. **Global flags go before the noun:** `dku --errors json recipe list`. Use `-o json` for scripting (pipe only to `jq`); `--compact` minifies and omits empty fields, and list commands take `--fields` to project columns.

## Chain to cut round-trips

Composability is the CLI's edge — do in one shell turn what separate calls can't:

- **Discover + extract:** `dku dataset schema DS -P PROJ -o json | jq -r '.[].name'`
- **Idempotent setup:** `dku project create P --if-not-exists && dku dataset create DS --if-not-exists -P P`
- **One verified unit:** create → configure → build → verify in a single `&&` chain, ending in a real-data check.

Do NOT chain multiple *unverified dependent* mutations — a 10-recipe `&&` chain hides which
upstream failed (silent cascade; rule 5). Verify real rows before chaining the next dependent stage.

## Silent-failure traps (DSS rarely errors loudly)

- **Unknown payload keys are ignored.** A wrong field name (`column` vs `inCol`, a mistyped
  processor param) is accepted as a no-op step — never trust exit 0; check real output rows.
- **`set-definition` normalizes and can drop fields; `get-definition` can be lossy** (omits
  scenario steps/triggers, app sections). Round-trip the full payload, re-read and diff after
  saving; never reconstruct from memory.
- **Wrong column / feature / LLM references don't error** — charts render blank, ML mis-guesses,
  prompts no-op. Verify against `dataset schema` / `--help` before trusting success.
- **`dataset delete` silently drops recipes that consume it** (no cascade prompt). Re-list after.

## Startup (substantive project work only)

1. `dku project list -o json | jq length`
2. If no project is specified, ask which to use.

Skip this for narrow reads.

## Capability → playbook

| User intent | Default capability | Playbook |
|---|---|---|
| Join, group, filter, sort, stack, distinct, window, top N, pivot, reshape | Visual recipe | `playbooks/tabular-flow.md` |
| Rename, parse/format dates, fill, split, normalize, derive columns | Prepare processor | `playbooks/tabular-flow.md` |
| SQL transformation; data quality rules; flow zones; build a pipeline | SQL recipe / DQ / flow | `playbooks/tabular-flow.md` |
| RAG over documents; LLM transform over rows; embed | Knowledge Bank / GenAI recipe | `playbooks/genai-agents.md` |
| Conversational tool use; deterministic multi-step agent; agent eval | Visual / Structured agent | `playbooks/genai-agents.md` |
| Project setup, variables, bundles, cross-project; scheduled/conditional rebuild | Project ops / Scenario | `playbooks/project-ops.md` |
| Dashboards, charts, insights; app designer; classification/regression/clustering | Dashboard / App / Visual ML | `playbooks/analytics-apps.md` |
| Define business entities, metrics, relationships, and golden queries for NL-to-SQL | Semantic model | `playbooks/semantic-layer.md` |
| Reusable packaged capability; webapp; admin/deploy/auth | Plugin / Webapp / Admin | `playbooks/extensions-admin.md` |
| Tracked approval workflow on a GOVERN node: blueprints, artifacts, sign-offs | Govern | `playbooks/govern.md` |

## References (open on demand for payload shapes / schemas)

| Need | Reference |
|---|---|
| Visual recipe JSON (join/group/window/filter/sort/pivot/topn/distinct/stack) + visual conditions | `references/visual-recipe-payloads.md` |
| Prepare processors: which one + params payload | `references/prepare-processors.md` |
| GREL formula syntax | `references/formulas.md` |
| Dataset connectors, schema, partitioning, plugin parameter types | `references/datasets-and-types.md` |
| Move local files ↔ DSS (local MCP file bridge) | `references/file-bridge.md` |
| Structured + visual agent block schema, graph, LLM tools | `references/agent-blocks.md` |
| Prompt (LLM) recipe payload schema | `references/prompt-recipe-payload.md` |
| Chart + dashboard/tile payload fields | `references/dashboards.md` |
| App Designer manifest + tile catalog | `references/app-designer.md` |
| Plugin structure, components, testing | `references/plugins.md` |
| Webapp backends, frontend, deploy | `references/webapps.md` |
| Govern blueprints, fields, workflow, sign-offs, hooks/actions, audit, custom-html embeds | `references/govern.md` |
| Model lifecycle (drift/retrain/MLflow/API serving), code envs, guardrails, semantic models, macros | `references/mlops.md` |
| Semantic model entity/attribute/metric/relationship/golden-query/glossary payload schemas + distinctValuesHandlingMode | `references/semantic-models.md` |
| Safety tiers, exit 77, admin lockout | `references/safety.md` |

## Routing notes

- Open exactly one playbook for the task; pull a reference only when you need a JSON payload.
- Don't browse the tree or re-read state you already fetched this session.
