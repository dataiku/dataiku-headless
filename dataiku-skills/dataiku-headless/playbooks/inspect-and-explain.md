# Inspect and explain

Read-only investigation: answer a question about a project, flow, dataset, or
object without building or changing anything. No Cobuild turn, no `allow_edit`, no
direct execution. If the question turns out to need a change, switch to
`build-via-cobuild.md`.

## The arc

**overview → structure → targeted reads → answer.**

1. **Overview.** `get_project_overview` for the project shape — it replaces listing
   datasets, recipes, scenarios, etc. one call at a time. For "which
   project?" start at `list_projects` / `count_projects`.
2. **Structure.** `get_flow_graph` when the question is about topology, build order,
   dependencies, branching, or re-convergence — it returns nodes, edges, and an
   ASCII tree, so read your own flow instead of reconstructing it.
3. **Targeted reads.** Drill only into what the question needs. Which read tool
   inspects which object type is the whole content of `../references/object-model.md`
   — use it instead of guessing a tool name. Common drills:
   - dataset shape → `get_dataset_info`; distributions/nulls → `get_dataset_profile`;
     raw values, delimiters, encodings → `get_dataset_sample`.
   - recipe wiring → `get_recipe_settings`; object metadata → `get_flow_object_metadata`.
   - run history / reliability → `get_scenario_run_history`, `list_jobs`,
     `get_job_status`, `get_job_log`.
   - quality → `list_data_quality_rules`, `get_data_quality_status`.
4. **Answer with analysis, not a dump.** Interpret in context: flag type mismatches
   (numbers or dates stored as strings), high null rates, duplicates, identifier-like
   columns, leakage risk, small samples, skew — whatever affects the user's next step.
   A list of columns is not an answer; a judgment about them is.

## Reading-budget discipline

Don't re-fetch state you already have this session. Don't fan out across every
object when the question names one. Don't open a reference you won't read a fact
from. The overview plus one or two targeted reads answers most questions.

## Cost-aware reads

- Keep samples small unless the user asks for a wide inspection.
- `test_connection` only when actively diagnosing connectivity — not as routine
  discovery.
- Don't fan out across every Data Collection unless the user needs an instance-wide
  catalog search; it is expensive on large instances.
- Treat redacted summaries as the source of truth. `get_connection_info` and the
  project-variable reads (`get_project_variables`, and the variables inside
  `get_project_overview`) redact secret-like values; `get_project_variables` also
  hides local variables unless you pass `include_local=true`. Never try to surface a
  secret-bearing field.

## Done when

- The user's question is answered from reads you actually ran, grounded in exact
  object names.
- Findings are interpreted (risks, anomalies, next step named), not dumped.
- Nothing was written, no Cobuild turn was opened, no `allow_edit` was set.
