---
name: jobs
description: Track and investigate Dataiku jobs. Use when an agent wants to list running and completed project jobs, check a job status, wait for completion, or inspect logs.
---

# Jobs

Use this skill to inspect and supervise project jobs that already exist rather than launch a new one.

## Job Concepts

A job is an execution record for a build, run, training, or deployment. A job can contain multiple activities, outputs, timings, and logs.

A `job_id` is the unit of supervision. Retain it after starting work so later turns can continue monitoring the same execution.

A wait timeout or interrupted client call ends observation, not necessarily execution. Treat the job as active until its status reaches a terminal state.

## Workflow

1. If the user wants to see recent project jobs, start with `list_jobs`.
2. If you already have a `job_id`, retain and reuse it rather than rediscovering the job.
3. If a synchronous build, run, training, or deployment call timed out or was interrupted before reaching a terminal state, switch here and continue from the existing `job_id` when available.
4. Use `wait_for_job` for normal follow-up on an active job.
5. Use `get_job_status` for lightweight polling, or `full=true` when activities, outputs, or timings matter.
6. Use `get_job_log` when execution logs or failure text are needed.

## Preferred Tools

- `list_jobs`
- `get_job_status`
- `wait_for_job`
- `get_job_log`

## Safety Rules

- If a tool returns `*_still_running` or the harness reports a timeout, treat the job as still active until proven otherwise.
- Do not assume a timed-out wait means the job failed; timeout is not failure.
- Do not assume a missing `job_id` means the job is gone; use `list_jobs` to rediscover recent project jobs first.
- If the current agent already started the job, keep supervising that same job instead of launching a replacement run.
- Do not start another overlapping build, run, or training job while the current one may still be running unless the user explicitly wants concurrent work and the targets are disjoint.
