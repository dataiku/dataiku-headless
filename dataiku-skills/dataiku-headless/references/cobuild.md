---
name: cobuild
description: Use Dataiku Cobuild for project-level asset creation, modification, and conversational co-development. Use when an agent needs to build or change project assets, continue a Cobuild conversation, or gather project context before making changes.
---

# Cobuild

Cobuild is Dataiku's AI building agent for co-developing Dataiku projects. It can build and modify flows, recipes, models, dashboards, webapps, notebooks, wiki content, agents, scenarios, and other project assets through a retained conversation.

Use this guide as the default path for project-level asset creation. This includes both broad requests such as "build me a flow for this use case" and narrow requests such as "create a filter recipe on dataset X".

## Cobuild Concepts

- A Cobuild conversation is stateful and bound to one project. Reuse its `conversation_id` for related work in that project.
- Conversations and retained turns are process-local: they live only in the running MCP server process. A server restart drops them, so start a new conversation rather than reusing an old `conversation_id`.
- `allow_edit_project` determines whether Cobuild may modify project assets. It defaults to `false` and is a per-message grant: pass `true` only for the single message that should be allowed to create or edit assets, and it does not carry over to later messages.
- One turn can run for minutes. If a call returns `status=timeout` (or a poll returns `in_progress`), its worker is still running: keep the returned `turn_id` and poll `get_cobuild_turn_status`. Never resend a timed-out instruction; the original worker is authoritative and a resend can duplicate a mutation.
- Only one turn runs per conversation at a time. A send or answer while a turn is in flight returns `status=busy` with that turn's `turn_id`; poll it instead of resending. There is also a global cap of 3 concurrent turns; a send that cannot claim a slot returns `status=error` with `error_kind=saturated`.
- Cobuild can inspect project context, propose changes, and make permitted changes through the same conversation.
- Deletion is a separate confirmation step. A request to edit does not authorize a broader or unexpected deletion. A deletion proposal carries a `confirmation_id` alongside `objects_to_delete` and `deletion_impacts`; approving requires passing that exact id back.

## When To Use This Skill

Use this guide when the user wants to:

- create project assets
- modify project assets through a conversational workflow
- have Cobuild inspect a project and then build or refactor something
- continue an existing Cobuild conversation

Do not use this guide when:

- the task is inspection-only and a direct read tool is the simpler path
- the task is not a project-level Cobuild workflow

## Workflow

1. Confirm the exact `project_key`.
2. When changing an existing asset, inspect it through its relevant object guide before preparing the Cobuild request. For greenfield work, ask Cobuild to inspect the necessary project context.
3. Reuse a known `conversation_id` only with its matching `project_key`. For a requested continuation without an available ID, use `list_cobuild_conversations` to rediscover it.
4. Start a conversation with `start_cobuild_conversation` only when no existing conversation applies.
5. Send the grounded request with `conversation_id` and `project_key`. Set `allow_edit_project=false` for inspection or explanation and `true` for an explicitly requested creation or modification.
6. If the call returns `status=timeout` or `status=busy`, retain its `turn_id` and poll `get_cobuild_turn_status` with the same `conversation_id` and `project_key`. Do not resend the instruction; the original worker is still authoritative.
7. Retain the returned `conversation_id` for follow-up work.
8. If Cobuild returns `status=needs_confirmation`, inspect the complete `objects_to_delete` and `deletion_impacts`, then pass its exact `confirmation_id` to `answer_cobuild_confirmation` with `APPROVE` or `CANCEL`.

## Prompt Guidance

- Prefer explicit Dataiku object names in prompts.
- For creation requests, describe the intended asset, inputs, outputs, and constraints clearly.
- If Cobuild needs project context, mention the relevant datasets, recipes, folders, models, dashboards, or other assets directly by name.
- For existing assets, include the configuration and constraints discovered through the relevant guide.

## Preferred Tools

| Goal | Tool |
| --- | --- |
| Start a new Cobuild conversation for a project | `start_cobuild_conversation` |
| Continue a Cobuild conversation | `send_cobuild_message` |
| Poll a long-running, timed-out, or busy turn | `get_cobuild_turn_status` |
| Approve or cancel a Cobuild delete confirmation request | `answer_cobuild_confirmation` |
| Rediscover retained conversations for a project | `list_cobuild_conversations` |

## Safety Rules

- Keep each `conversation_id` paired with its matching `project_key`.
- Use `allow_edit_project=true` only when the user has explicitly requested a creation or modification. It is a per-message grant, so it must be set again on each message that should be allowed to write.
- A `status=timeout` ends only the MCP client's wait, not the worker. Poll the returned `turn_id` with `get_cobuild_turn_status`; never resend a timed-out mutation.
- Treat `error_kind=transport_outcome_unknown` as ambiguous. Inspect project state before deciding whether to retry any mutation, and do not blindly resend.
- Conversations and turns do not survive a server restart. If a `turn_id` or `conversation_id` is reported unknown, start a new conversation rather than resending.
- `send_cobuild_message` may return `status=needs_confirmation`, with the exact proposal in `objects_to_delete` and `deletion_impacts` and its `confirmation_id`. `answer_cobuild_confirmation` requires that exact `confirmation_id`, so read the proposal before approving.
- Approve a deletion only when its scope clearly matches the user's stated intent. If it is broader, ambiguous, or surprising, clarify with the user before responding.
- Before triggering a build-affecting prompt, check `./jobs.md` if there's any chance the same flow objects are already mid-build elsewhere — don't kick off overlapping work.
- If Cobuild's coverage can't do what's needed and no read tool covers it either, stop and report the gap rather than falling back to raw `dataikuapi`/Python/REST calls — those aren't available in this environment.
- There is no close or delete conversation tool.
