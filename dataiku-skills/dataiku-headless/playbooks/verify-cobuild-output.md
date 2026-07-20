# Verify Cobuild output

Proving a delegated result is real. Cobuild's `completed` status is testimony;
this playbook is how you turn it into evidence (rule 5; `../soul.md`, "Trust nothing
you didn't read").
Run it after every build unit, not only at the end.

## Start from the report, not from scratch

Diff the reported objects and row counts against intent, and note anything Cobuild
could not complete. Use that inventory to scope the targeted reads below; it does
not replace them.

## What to check, by claim

Match the check to what Cobuild claimed it did:

| Cobuild claimed… | Prove it with |
|---|---|
| built / transformed a dataset | `get_dataset_sample` (real values), `get_dataset_metrics` (row count), `get_dataset_profile` (nulls, distributions) |
| changed the flow's shape | `get_flow_graph` — diff the nodes/edges/build-order against what you expected |
| a build or run succeeded | `list_jobs` → `get_job_status`; `get_job_log` on any failure or 0-row output |
| added quality validation | `list_data_quality_rules`, `get_data_quality_status` |
| trained or scored a model | `../references/ml-and-genai-objects.md` — inspect the model via a read-only Cobuild turn, and read its evaluation artifacts (evaluation store, metrics, scored-output rows) |
| built or changed an agent | test it with several skeptical queries; check tools fired and citations are real |
| finished the project | `audit_project`, optionally with a contract |

## Grain and emptiness — the silent failures

DSS rarely errors loudly, so the dangerous outcomes are the quiet ones:

- **Empty output is data, not success.** A 0-row dataset with a `completed` status
  is a failed unit. Read the row count, don't trust the status.
- **Check row counts at every grain change.** A join on a non-unique key multiplies
  rows and poisons every number downstream, silently. Confirm the grain is what you
  asked for after any join or aggregation.
- **Wrong references no-op.** A prompt that named a column Cobuild couldn't find may
  come back "done" with that step quietly skipped. Verify the actual output columns
  against the intent, not the report.

## audit_project as the contract check

`audit_project` audits the **flow** — datasets, recipes, zones, wiki — bucketing its
verdict into structure, documentation, evidence, and maintainability. Pass a contract
to assert the specific outputs you delegated exist with the expected shape — that
turns "the project looks fine" into "the outputs I asked for are present and
correct". It does **not** judge models, agents, or dashboards; verify those from the
rows above (targeted reads and read-only Cobuild turns). A clean audit is the floor;
a `get_flow_graph` read you can explain branch by branch is the ceiling (`../soul.md`,
"Finish gold").

## On failure

Send a corrective follow-up on the **same** `conversation_id` naming exactly what's
wrong (the check that failed, the expected vs actual). Do not open a fresh
conversation, and do not proceed to a dependent unit until this one passes.

## Done when

- Every claim Cobuild made about this unit was confirmed by a read, not accepted
  from its status.
- Row counts were checked at every grain change; no output is unexpectedly empty.
- For a finished project, `audit_project` (with a contract on the delegated outputs)
  reports no fail-severity findings.
