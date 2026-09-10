---
name: jobs
description: Run existing Dataiku datasets or recipes, then track, investigate, or abort their jobs. Use when an agent wants to execute an existing Flow asset, list jobs, check status, wait for completion, inspect logs, or stop a running job.
---

# Jobs

Use this guide to execute existing datasets or recipes and supervise the resulting Dataiku job. Asset creation and configuration changes still route through Cobuild.

## Job Concepts

A job is an execution record for a build, run, training, or deployment. A job can contain multiple activities, outputs, timings, and logs.

A `job_id` is the unit of supervision. Retain it after starting work so later turns can continue monitoring the same execution.

A wait timeout or interrupted client call ends observation, not necessarily execution. Treat the job as active until its status reaches a terminal state.

## Workflow

1. Inspect the target and check recent/running jobs before starting work.
2. Use `build_datasets` for one or more existing dataset outputs, or `run_recipe` for one existing recipe. Both default to returning immediately with one `job_id`.
3. Retain and reuse that `job_id` rather than rediscovering or restarting the job.
4. Use `wait_for_job` for normal follow-up on an active job.
5. Use `get_job_status` for lightweight polling, or `full=true` when activities, outputs, or timings matter.
6. Use `get_job_log` when execution logs or failure text are needed.
7. Use `abort_job` to stop a job that must not continue, then confirm the terminal state before any replacement run.

## Preferred Tools

- `list_jobs`
- `build_datasets`
- `run_recipe`
- `get_job_status`
- `wait_for_job`
- `get_job_log`
- `abort_job`

## Safety Rules

- If a tool returns `*_still_running` or the harness reports a timeout, treat the job as still active until proven otherwise.
- `build_datasets` starts all requested outputs in one job. Do not split them into overlapping calls.
- If a start request raises before returning a `job_id`, inspect recent jobs before retrying; Dataiku may have accepted the request before the connection failed.
- A `*_poll_failed` response means the job started but polling failed. Keep its `job_id` and inspect it with `get_job_status` or `wait_for_job`; do not restart.
- Do not assume a timed-out wait means the job failed; timeout is not failure.
- Do not assume a missing `job_id` means the job is gone; use `list_jobs` to rediscover recent project jobs first.
- If the current agent already started the job, keep supervising that same job instead of launching a replacement run.
- Do not start another overlapping build, run, or training job while the current one may still be running unless the user explicitly wants concurrent work and the targets are disjoint.
- `abort_job` stops a job that must not continue. `abort_still_pending` means the abort was accepted but the job is not terminal yet; confirm with `get_job_status` before a replacement run. An abort does not roll back what the job already wrote.
