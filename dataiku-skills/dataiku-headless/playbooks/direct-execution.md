# Direct execution

The three sanctioned non-Cobuild actions, and when to reach for them instead of
delegating.

## The three tools

`build_datasets`, `run_recipe`, `run_scenario` execute assets that **already
exist** and whose behavior is **already decided**. They carry no design decision —
that is the entire reason they bypass Cobuild.

## When direct beats delegating

Reach for a direct tool only when there is nothing to design:

- **Rebuild** a dataset or flow after an upstream refresh → `build_datasets`.
- **Re-run** an existing recipe to refresh its output → `run_recipe`.
- **Trigger** an existing scenario on demand → `run_scenario`.

If the request changes *what* an asset does — new columns, new logic, new steps,
new schedule — that is construction: delegate it (`build-via-cobuild.md`).

## The job-follow loop

All three default to **not waiting**. Firing one returns an id, not a
result — driving it to completion is your job:

1. Fire the tool. Retain the returned id: a **job id** from `build_datasets` /
   `run_recipe`, a **scenario run id** from `run_scenario`.
2. For builds and recipe runs, follow the job id with `wait_for_job` (normal
   follow-up) or `get_job_status` (lightweight poll; ask for full detail when
   activities, outputs, or timings matter). Read `get_job_log` on failure.
3. For scenarios, follow the run with `get_scenario_run_history`. A scenario run is
   not a DSS job — it settles there, not through `wait_for_job`.
4. **A timeout or interrupted wait ends observation, not execution.** Treat the job
   or scenario run as active until its status reaches a terminal state; re-attach to
   the same id rather than firing a replacement run.

## Don't start overlapping work

Never launch a build, run, or scenario against flow objects that may already be
mid-build — whether the other run is a direct execution or a Cobuild turn. Check
`list_jobs` first if there's any chance. Detail in
`../references/safety-and-confirmations.md`.

## Done when

- The intended asset was executed by a direct tool only because it already existed
  with decided behavior — no design decision was smuggled into an execution.
- The job or scenario run reached a terminal state, observed via `wait_for_job` /
  `get_job_status` / `get_scenario_run_history` — not assumed from the launch call.
- The refreshed output was checked on real data (see `verify-cobuild-output.md`).
