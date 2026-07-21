# Verify Cobuild output

A completed Cobuild turn is a claim about what finished. This playbook matches
that claim to independent DSS evidence. Run the relevant check after each
delegated unit, not only at the end.

## Match the check to the claim

| Cobuild claimed | Verify with |
|---|---|
| Built or transformed a dataset | `get_dataset_sample`, `get_dataset_metrics`, and, when distribution or null behavior matters, `get_dataset_profile` |
| Changed Flow structure | `get_flow_graph`; compare nodes, edges, and build order with the requested change |
| A build or recipe run succeeded | `get_job_status`; use `get_job_log` on failure or unexpected output |
| Added Data Quality checks | `list_data_quality_rules`, then the applicable rule, result, history, and status reads; rule meanings are in `../references/objects/data-quality-rule-types.md` |
| Trained or changed an ML model | `get_ml_analysis_summary`, `list_ml_analysis_models`, `get_ml_model_details`, saved-model settings, and evaluation artifacts |
| Built or changed an agent | Agent settings plus Agent Review tests, repeated runs, and run results |
| Built or changed a live WebApp | Saved WebApp settings plus `get_webapp_state` |
| Finished a Flow deliverable | `audit_project`, optionally with an explicit output contract |

The object-specific calls are indexed in
`../references/object-model.md` and the ML/agent sequence is detailed in
`../references/ml-and-genai-objects.md`.

## Grain and emptiness

The most costly data failures often finish without a transport or job error:

- A zero-row output is a real result, not evidence that the requested unit works.
- Check counts after any join, aggregation, deduplication, or other grain change.
  A non-unique join key can multiply rows without failing the job.
- Check the actual output columns and values. A wrong object or column reference
  can leave a requested step absent even when the wider build completes.
- Treat missing or unreadable evidence as unknown. Do not turn a warning,
  timeout, truncated result, or unavailable metric into a pass.

## Use audit_project for its contract

`audit_project` checks bounded Flow evidence for datasets, recipes, topology,
zones, and wiki structure. DSS consistency failures and an explicit caller
contract affect the blocking verdict. Naming, documentation, zoning, orphan, and
similar maintainability findings are advisory; report them as advice unless the
user made one an explicit requirement.

The audit does not certify models, agents, scenarios, connections, or live
application behavior. Use their targeted reads.

## On failure

Send a corrective follow-up on the same `conversation_id`. State the observed
evidence, expected result, and exact object involved. Do not proceed to a
dependent unit until the failed prerequisite is understood or corrected.

## Done when

- Each material claim has matching independent evidence.
- Output grain, row presence, and required fields have been checked where relevant.
- Any explicit audit contract passes.
- Advisory findings are reported without presenting them as objective failures.
