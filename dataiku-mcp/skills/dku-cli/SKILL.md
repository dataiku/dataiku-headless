---
name: dku-cli
description: Operate Dataiku DSS end to end with the `dku` CLI. Use whenever the task touches Dataiku or DSS in any form — building or reviewing flows, datasets, visual or code recipes, jobs, scenarios, dashboards, visual ML, LLM/GenAI agents, knowledge banks, semantic models, plugins, webapps, Govern, or instance admin — even if the user doesn't name the CLI. Also use when deciding which DSS-native capability fits before writing custom code. NOT for migrating legacy SAS/Alteryx/KNIME/Excel workflows into DSS (use the migration skill).
license: Apache-2.0 (see repository LICENSE)
metadata:
  author: dataiku
  tags: dataiku, dss, cli
---

# Dataiku DSS

Use `dku` for both capability choice and execution. Read **one playbook** per task,
get exact flags from `--help`, open a reference only for JSON payload shapes. Don't browse
the tree or re-read state you already fetched this session.

## Operating thesis

Dataiku's product is **work that subject matter experts & data scientists can efficiently review**. Enterprises hold humans
accountable for decisions, and humans can only be accountable for work they can follow —
everyone can read a visual flow. When agents do the building, human review becomes the bottleneck, and the
SME who opens your flow tomorrow is your real user. Build accordingly:

- **The flow is the deliverable.** Correct outputs in an unreadable flow = failed work.
  Zones, verb-first recipe names, descriptions, and inspectable intermediate datasets
  are load-bearing, not polish.
- **Every drop to code loses reviewers.** The capability ladder (rule 1) is a fidelity
  ladder, not a style guide. Your training pulls you toward Python/SQL — "code would be
  cleaner here" is the exact failure mode this skill exists to prevent. Drop a rung only
  when the capability genuinely doesn't exist above it.
- **Each project type has a native reviewable shape.** Prep = visual recipes ·
  ML/statistics = visual ML + evaluation stores (not notebook sklearn) · GenAI =
  visual/structured agents + agent review + evals (not a framework in a code recipe) ·
  delivery = dashboards, semantic models & Agent Hub.
- **Shoot for gold, not for "it ran".** The bar is a project a Dataiku expert would
  proudly show to business leadership: visible validation, a zoned flow, a wiki. Put ambition
  into the quality and completeness of what was asked — never into silent scope creep.

**Long-running build? Read `soul.md` first** — any multi-stage project (new flow,
migration, demo, agent system). It is the judgment layer: simple-first escalation,
stage-gate validation, pre-processing trade-offs, and the gold finishing standard.
Skip it for one-shot reads and single commands.

## Exact flags live in `--help`, not in docs

`--help` always returns compact machine-readable JSON:

- `dku --help` → groups + root commands + global options
- `dku recipe --help` → terse one-line signature per command in the group
- `dku recipe create-join --help` → full args, flags, types, defaults for one command

Never guess flags and never document them here — drill into command `--help`.

## Don't know which command? Check the index once

`references/command-index.md` lists every group/command with a one-line description,
generated from the same source as `--help`. Use it when the capability table below has no
row for the task, or the task spans domains you haven't touched yet — instead of
re-deriving structure by drilling `--help` group by group.

Know the keyword? `grep -i <keyword> references/command-index.md` (or `dku commands |
grep`) and skip the rest of the file. Genuinely don't know what you're looking for? Read
the whole file once — still cheaper than the round trips it replaces. Either way, once you
have the exact command, go straight to `dku <group> <command> --help` for flags.

## Permanent rules

1. **Prefer DSS-native features over custom code.** Capability ladder: visual recipe →
   GenAI recipe → AutoML/visual ML → agents & knowledge banks → scenario → SQL recipe →
   Python/R recipe (last resort). Take the first rung that fits (the *why* is the
   operating thesis above).
2. **Inspect before you mutate.** Substantive work: list projects
   (`dku --format json project list`) and ask which if none specified, then
   `dku project inspect`. Skip both for narrow reads.
3. **Sample and schema-check inputs** before transforming.
4. **Build with** `dku job run --type RECURSIVE_BUILD --wait`. Output schemas auto-update by default; with `--wait` the changes are reported per dataset; add `--no-auto-update-schema` only to preserve a partitioned or hand-curated schema.
5. **Verify with real data.** Exit 0 is not proof; empty arrays are data, not success. Check row counts, schema, and sample values.
6. **Review the flow as the reviewer will.** Before declaring a project done, run the
   finish gate — `dku project audit -P PROJ` — one read-only verdict over structure,
   docs, evidence, and maintainability that names what's wrong and the fix command
   (`--contract @f` adds value-parity checks). Then look with your own eyes: `dku flow
   visualize` (ASCII DAG) + the flow-review pass (tabular-flow playbook). Zones, names,
   descriptions are part of done, not polish.
7. **Test agents.** Exit 0 is not proof; actually test and validate the agents you
   create — sample queries at minimum, an agent-review setup for anything substantial.
8. **Output is machine-readable by default — skip format flags on normal reads.**
   Lists render as TSV (header row of column keys, then rows), single objects as
   compact JSON. Data goes to stdout, messages/hints to stderr — stdout is always
   pipe-safe. Add a flag only to *parse or round-trip*, before the noun:
   `--format ids` for one id per line (piping), `--format json` for jq filters
   and definition round-trips. List commands take `--fields` to project columns.
9. **One project? Set it once:** `export DKU_PROJECT=PROJ` — every project-scoped
   command picks it up; drop `-P` from each call.

## Chain to cut round-trips

Composability is the CLI's DNA - do in one shell turn what separate calls can't:

- **Discover + extract:** `dku --format ids dataset list -P PROJ | while read ds; do ...; done`
- **Idempotent setup:** `dku project create P --if-not-exists && dku dataset create DS --if-not-exists -P P`
- **One verified unit:** create → configure → build → verify in a single `&&` chain, ending in a real-data check.
- **Batch discovery, not just execution:** need flags for several sibling commands? Chain the
  `--help` calls instead of one probe per turn — `dku dq create --help && dku dq compute --help
  && dku dq results --help`. One round trip, N payloads.

Do NOT chain multiple *unverified dependent* mutations — a 10-recipe `&&` chain hides which
upstream failed (silent cascade; rule 5). Verify real rows before chaining the next dependent stage.

## Silent-failure gotchas (DSS rarely errors loudly)

- **Unknown payload keys are ignored.** A wrong field name (`column` vs `inCol`, a mistyped
  processor param) is accepted as a no-op step — never trust exit 0; check real output rows.
- **`set-definition` normalizes and can drop fields; `get-definition` can be lossy** (omits
  scenario steps/triggers, app sections). Round-trip the full payload, re-read and diff after
  saving; never reconstruct from memory.
- **Wrong column / feature / LLM references don't error** — charts render blank, ML mis-guesses,
  prompts no-op. Verify against `dataset schema` / `--help` before trusting success.
- **`dataset delete` silently drops recipes that consume it** (no cascade prompt). Re-list
  after — detail and recovery in `references/safety.md`.

## Capability → playbook

| User intent | Default capability | Playbook |
|---|---|---|
| Join, group, filter, sort, stack, distinct, window, top N, pivot, reshape | Visual recipe | `playbooks/tabular-flow.md` |
| Rename, parse/format dates, fill, split, normalize, derive columns | Prepare processor | `playbooks/tabular-flow.md` |
| SQL transformation; data quality rules; flow zones; flow review/audit; build a pipeline | SQL recipe / DQ / flow | `playbooks/tabular-flow.md` |
| RAG over documents; LLM transform over rows; embed | Knowledge Bank / GenAI recipe | `playbooks/genai-agents.md` |
| Conversational tool use; tool-calling loop (ReAct) → `dku agent create-react`; deterministic multi-step agent; agent eval; surface/deliver agents to end users (Agent Hub) | Visual / Structured agent | `playbooks/genai-agents.md` |
| Project setup, variables, bundles, cross-project; scheduled/conditional rebuild | Project ops / Scenario | `playbooks/project-ops.md` |
| Dashboards, charts, insights; app designer; classification/regression/clustering | Dashboard / App / Visual ML | `playbooks/analytics-apps.md` |
| Define business entities, metrics, relationships, and golden queries for NL-to-SQL | Semantic model | `playbooks/semantic-layer.md` |
| Reusable packaged capability; webapp; admin/deploy/auth | Plugin / Webapp / Admin | `playbooks/extensions-admin.md` |
| Tracked approval workflow on a GOVERN node: blueprints, artifacts, sign-offs | Govern | `playbooks/govern.md` |

## References (open on demand for payload shapes / schemas)

| Need | Reference |
|---|---|
| Every group/command in one read — cross-domain discovery, no row above fits | `references/command-index.md` |
| Visual recipe JSON (join/group/window/filter/sort/pivot/topn/distinct/stack) + visual conditions | `references/visual-recipe-payloads.md` |
| Visual recipe silent-failure traps (spurious unsaved-changes prompt, no-op steps, wrong-shape config, schema/type drift, grouping traps) | `references/visual-recipe-traps.md` |
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
| Model lifecycle (drift/retrain/MLflow/API serving), code envs, guardrails, macros | `references/mlops.md` |
| Semantic model entity/attribute/metric/relationship/golden-query/glossary payload schemas + distinctValuesHandlingMode | `references/semantic-models.md` |
| Agent Hub (deliver agents to end users): the `/api/admin/config` endpoint vs the API-key 401, what `dku agent-hub` can/can't do, the read-only export path | `references/agent-hub.md` |
| Visual Graph plugin (Kuzu): editor webapp, publish, Cypher recipes, graph-search agent tool | `references/visual-graph.md` |
| Snowflake ML (`ANOMALY_DETECTION`/`FORECAST`) from DSS SQL | `references/snowflake-ml.md` |
| Safety tiers, exit 77, admin lockout | `references/safety.md` |
