---
name: cobuild
description: Use Dataiku Cobuild for project-level asset creation, modification, and conversational co-development. Use when an agent needs to build or change project assets, continue a Cobuild conversation, or gather project context before making changes.
---

# Cobuild

Cobuild is Dataiku's AI building agent for co-developing Dataiku projects. It can build and modify flows, recipes, models, dashboards, webapps, notebooks, wiki content, agents, scenarios, and other project assets through a retained conversation.

Use this guide as the default path for project-level asset creation. This includes both broad requests such as "build me a flow for this use case" and narrow requests such as "create a filter recipe on dataset X".

## Cobuild Concepts

- A Cobuild conversation is stateful and bound to one project. Reuse its `conversation_id` for related work in that project.
- `allow_edit_project` determines whether Cobuild may modify project assets. Use `false` for inspection or explanation and `true` only for an explicitly requested creation or modification.
- Cobuild can inspect project context, propose changes, and make permitted changes through the same conversation.
- Deletion is a separate confirmation step. A request to edit does not authorize a broader or unexpected deletion.

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
6. Retain the returned `conversation_id` for follow-up work.
7. If Cobuild returns a delete confirmation request, inspect the deletion details and respond through `answer_cobuild_confirmation`.

## Turn Scope and Waiting

- Keep each turn to one coherent unit that fits the server-side time cap; split wide or repetitive work across turns.
- If `send_cobuild_message` returns `status: timeout` with `overdue: false`, do not resend or defer waiting. Poll `get_cobuild_turn_status` inside the same run with the original `conversation_id` and `turn_id` until the turn settles.

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
| Poll a turn that has not settled yet | `get_cobuild_turn_status` |
| Approve or cancel a Cobuild delete confirmation request | `answer_cobuild_confirmation` |
| Rediscover retained conversations for a project | `list_cobuild_conversations` |

## Safety Rules

- Keep each `conversation_id` paired with its matching `project_key`.
- Use `allow_edit_project=true` only when the user has explicitly requested a creation or modification.
- `send_cobuild_message` may return `is_confirmation_request=true`, with deletion details in `objects_to_delete` and `deletion_impacts`.
- Approve a deletion only when its scope clearly matches the user's stated intent. If it is broader, ambiguous, or surprising, clarify with the user before responding.
- Before triggering a build-affecting prompt, check `./jobs.md` if there's any chance the same flow objects are already mid-build elsewhere — don't kick off overlapping work.
- If Cobuild's coverage can't do what's needed and no read tool covers it either, stop and report the gap rather than falling back to raw `dataikuapi`/Python/REST calls — those aren't available in this environment.
- There is no close or delete conversation tool.
