# Build via Cobuild

The flagship arc: turn a build request into verified, reviewable assets by
delegating to Cobuild and checking its work. For a build with several dependent
delegate-and-verify cycles, read `../soul.md` first. For the judgment behind the
sequence and prompt structure, read `../references/cobuild-prompt-patterns.md`.

## The arc

**orient → decompose → ground → plan read-only → delegate the build → settle →
verify → audit.**

1. **Orient.** `get_project_overview` on the target project. Add
   `get_flow_graph` when the change touches an existing flow — you need the build
   order and the exact upstream/downstream names before you write a prompt.
2. **Decompose.** Split the goal into units you can each verify with a read
   afterward. One unit means one prompt and one named check. Do not batch several
   dependent stages into one delegation.
3. **Ground the prompt in real names.** Every dataset, recipe, folder, model,
   connection, or agent the task depends on goes into the prompt *by the exact name
   you read*, never an assumed one. Inspect existing assets first (see
   `inspect-and-explain.md`); for greenfield work, tell Cobuild what to inspect.
4. **Get a read-only plan first.** Send the task with `allow_edit_project=false`
   and ask Cobuild for its plan — which recipes, which schema, which zone. Review it
   against intent before anything is written. This is free insurance on any
   non-trivial build.
5. **Delegate the build.** Re-send on the same `conversation_id` with
   `allow_edit_project=true` once the plan is sound. Keep the id paired
   with the project key.
6. **Settle the turn** — see the timeout/poll protocol below.
7. **Verify with real data.** Run the checks you named in step 2; see
   `verify-cobuild-output.md`. If a unit fails, send a corrective follow-up on the
   same conversation — don't proceed to the next dependent unit.
8. **Audit the Flow.** When the project is done, run `audit_project`, optionally
   with a contract asserting the outputs you delegated. Treat DSS consistency and
   contract failures as blockers; review maintainability warnings as advice.

## Timeout / poll protocol

A Cobuild turn returns one of: `completed` · `in_progress` · `needs_confirmation`
· `error` · `timeout` · `busy`.

- **`timeout` is not failure.** The turn is retained in the server process (a
  restart loses an unpolled turn). Settle it with `get_cobuild_turn_status` —
  poll until it reaches a terminal status.
- **`busy` means you already have a turn in flight.** If you send or answer while a
  turn is still running for that conversation, the server refuses the new
  instruction and returns the existing `turn_id` with `status: busy` — nothing is
  double-run. Poll that `turn_id` with `get_cobuild_turn_status`; do not resend.
- **Never re-send while a turn is `in_progress`.** A second message does not cancel
  or race the first — the server serializes turns and rejects it as `busy`,
  returning the existing `turn_id`. Poll the existing turn instead.
- **`completed` is Cobuild's claim, not your proof.** Move to verify (step 7).
- **`error`** — read `error_kind` before you react, because not every error is safe
  to re-send.
  - A **definitive DSS error** (Cobuild actually rejected the turn: bad prompt,
    missing edit permission, unknown object name) → fix what the message says is
    wrong and re-send on the same conversation.
  - **`error_kind: transport_outcome_unknown`** (a connection-level failure — the
    request may have reached DSS and the build may have partly landed) → **do not
    blindly re-send.** A resend can double-run a build that already ran. First find
    out what actually happened: inspect the project, or send a **read-only**
    follow-up (`allow_edit_project=false`) on the same conversation, then decide.

## Escalating allow_edit

`allow_edit_project` is a per-message grant, default false. The read-only
plan (step 4) and the build (step 5) are the same conversation with the flag off
then on. Inspection turns, follow-up questions, and "explain what you'd change"
all stay false. Only the message that should actually write assets carries true.

## When Cobuild returns needs_confirmation (deletions)

A build grant does not authorize deletion — DSS gates that separately. When a turn
returns `needs_confirmation`, follow the deletion protocol in
`../references/safety-and-confirmations.md`: inspect `objects_to_delete` and
`deletion_impacts`, then approve through `answer_cobuild_confirmation` — passing the
`confirmation_id` from that result, which is required and is your exact-match proof
you inspected this specific deletion — only when the scope matches the user's stated
intent. If it is broader, ambiguous, or surprising, surface it to the user before
responding — do not approve to keep the build moving.

## Done when

- Every decomposed unit was delegated, its turn reached a terminal status, and its
  named check passed on real data — not a `completed` status alone.
- No turn was re-sent while `in_progress`; every `timeout` was settled via
  `get_cobuild_turn_status`.
- Any deletion was confirmed only after its scope was checked against stated intent.
- `audit_project` reports no fail-severity findings, and any advisory findings
  have been reviewed against the user's goal.
