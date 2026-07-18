# Safety and confirmations

The fragile, irreversible operations and their one safe path. Open this when a
Cobuild turn asks to delete, when a build might overlap another, or when switching
instances.

## Deletion confirmation protocol

A build grant (`allow_edit_project=true`) does **not** authorize deletion — DSS
gates deletes separately, and an edit request never implies a broader or unexpected
delete.

1. A `send_cobuild_message` turn returns status `needs_confirmation` carrying
   `objects_to_delete` and `deletion_impacts`. Read both — the impact list is what
   the deletion cascades into, not just the named target.
2. Decide against the user's stated intent. **Approve only when the scope clearly
   matches what the user asked for.** If it is broader, ambiguous, or surprising,
   stop and surface it to the user before responding — never approve to keep a build
   moving.
3. Respond with `answer_cobuild_confirmation`, choice `APPROVE` or `CANCEL`, using
   the `confirmation_id` from the turn. The `confirmation_id` is restorable after a
   restart, so a confirmation you couldn't answer in-session can still be settled —
   `list_cobuild_conversations` rediscovers the conversation.

Treat deletion as destructive even though Cobuild manages the mechanics. Migration
cleanup deletes only this migration's failed attempts and orphans, never pre-existing
assets (`../playbooks/migrate.md`).

## Overlapping builds

Never start a build, run, or scenario against flow objects that may already be
mid-build — whether the other run is a direct execution or a Cobuild turn.
Concurrent writes to the same path corrupt build state.

- Check `list_jobs` first if there's any chance the same objects are live.
- For linearly dependent stages, complete delegate→verify (or execute→verify) for
  each before starting the next — don't batch-create then build all at once.
- **A timeout is not failure and not completion.** A timed-out Cobuild turn is
  retained server-side (settle with `get_cobuild_turn_status`); a timed-out or
  interrupted job is still running (re-attach to its handle via `wait_for_job` /
  `list_jobs`). Treat the work as active until a terminal status proves otherwise —
  a replacement run started on that assumption is an overlapping build.

## No raw API fallback

If Cobuild can't do what's needed and no read tool covers it either, **stop and
report the gap**. There is no `dataikuapi`/Python/REST escape hatch in this
environment — inventing one is not an option (rule 2).

## Instance switches

`switch_instance` changes which DSS instance every subsequent tool targets;
`get_current_instance` confirms where you are and `list_instances` shows the
options. Conversation ids, job ids, and object names are **per-instance** — a
`conversation_id` from one instance is meaningless on another. Confirm the current
instance before acting on ids you retained earlier, and switch deliberately, not as
a side effect.

## Data and secrets

- Never set overwrite / replace existing data without explicit user intent — an edit
  request is not replacement authorization.
- Never expose secret-bearing connection fields or unredacted runtime logs; the
  inspection summaries are already redacted.
- Never place credentials, tokens, or secrets in project-library source.
