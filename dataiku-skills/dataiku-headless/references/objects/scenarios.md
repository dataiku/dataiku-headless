# Scenarios

A scenario combines ordered steps, automatic triggers, and completion reporters.

| Part | Meaning |
|---|---|
| Steps | Builds, model work, data movement, exports, code, or notifications performed by a run |
| Triggers | Schedules or project events that can start a run |
| Reporters | Completion notifications sent through configured messaging channels |
| Delayed-trigger behavior | What happens when a trigger fires while a prior run is active |
| Run history | Success, warning, failure, abort, timing, and recurring reliability evidence |

`active` controls whether automatic triggers can fire; it does not delete the
scenario. Preserve existing triggers, reporters, and delayed-trigger behavior
unless the user asks to change them.

A manual `run_scenario` returns a scenario `run_id`; a `trigger_fire_id` is
not interchangeable. If a trigger request raises or a bounded wait ends, inspect
the same scenario's history before retrying because DSS may already have accepted
the run.
