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
3. Respond with `answer_cobuild_confirmation`, choice `APPROVE` or `CANCEL`, and the
   `confirmation_id` from that turn. Passing `confirmation_id` is **required** and
   must exact-match the pending confirmation — so it doubles as proof you inspected
   *this* specific deletion rather than approving blind. The pending confirmation is
   process-local: settle it in the same server session. A restart drops it (along with
   the conversation), so if you cannot answer before then, re-inspect and re-delegate
   in a fresh conversation.

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
- **A timeout is not failure and not completion.** A timed-out Cobuild turn keeps
  running on its worker in the same server process (settle with
  `get_cobuild_turn_status`); a timed-out or interrupted job is still running
  (re-attach to its handle via `wait_for_job` / `list_jobs`). Treat the work as active
  until a terminal status proves otherwise — a replacement run started on that
  assumption is an overlapping build. **Never resend a timed-out turn** — the worker
  may still be applying it, and a resend can duplicate the mutation.

## What happens on a restart

Everything Cobuild is **process-local**: conversations, their retained turns, and any
pending deletion proposal live only in the running server process. There is no durable
store and no cross-process coordination. A server restart drops all of it — a
`conversation_id` from a previous process is unknown, `list_cobuild_conversations`
lists only what is live now, and an unanswered deletion confirmation is gone. After a
restart, start a new conversation and re-inspect the project to learn what actually
landed before delegating again.

## No raw API fallback

If Cobuild can't do what's needed and no read tool covers it either, **stop and
report the gap**. There is no `dataikuapi`/Python/REST escape hatch in this
environment — inventing one is not an option.

## Instance switches

`switch_instance` changes which DSS instance every subsequent tool targets;
`get_current_instance` confirms where you are and `list_instances` shows the
options. Conversation ids, job ids, and object names are **per-instance** — a
`conversation_id` from one instance is meaningless on another. Confirm the current
instance before acting on ids you retained earlier, and switch deliberately, not as
a side effect.

## Data and secrets

- Never set overwrite / replace existing data without explicit user intent — an edit
  request is not replacement authorization. `upload_file_to_managed_folder` defaults
  `overwrite=false` and refuses to replace a file already at the target path unless
  you opt in explicitly.
- Never expose secret-bearing connection fields or unredacted runtime logs; the
  inspection summaries are already redacted.
- Never place credentials, tokens, or secrets in project-library source.
