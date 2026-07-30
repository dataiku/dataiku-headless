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
- One operation runs at a time per conversation. A completed result must be observed before starting the next operation.
- Cobuild can inspect project context, propose changes, and make permitted changes through the same conversation.
- Deletion confirmations and questions are separate response steps bound to their exact `turn_id`. A request to edit does not authorize a broader or unexpected deletion.
- Conversations and turns are retained only in the MCP server process and are lost when it restarts.

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
6. A message, confirmation answer, or question answer waits for up to 240 seconds by default. If it returns `status=queued` or `status=in_progress`, call `get_cobuild_turn_status` with its exact `turn_id`; never resend the instruction.
7. If an interrupted call loses its response, use `list_cobuild_conversations` to recover the conversation's current turn ID and poll it before doing anything else.
8. Retain the returned `conversation_id` for follow-up work.
9. If Cobuild returns a delete confirmation request, inspect the deletion details and pass its exact `turn_id` to `answer_cobuild_confirmation`.
10. If Cobuild returns a question request, inspect its `question` object and pass its exact `turn_id` plus an explicit `answers` list to `answer_cobuild_question`. Use `answers=[]` when rejecting the question.

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
| Approve or cancel a Cobuild delete confirmation request | `answer_cobuild_confirmation` |
| Answer a Cobuild question request | `answer_cobuild_question` |
| Poll a retained Cobuild operation | `get_cobuild_turn_status` |
| Rediscover retained conversations for a project | `list_cobuild_conversations` |

## Safety Rules

- Keep each `conversation_id` paired with its matching `project_key`.
- Use `allow_edit_project=true` only when the user has explicitly requested a creation or modification.
- `send_cobuild_message` defaults `allow_edit_project` to `false`.
- `send_cobuild_message` may return `is_confirmation_request=true`, with deletion details in `objects_to_delete` and `deletion_impacts`.
- `send_cobuild_message` may return `is_question_request=true`, with its title and answer constraints in `question`.
- Answer only with the exact current confirmation `turn_id`. Old, duplicate, and mismatched turn IDs are rejected.
- Answer questions only with their exact current `turn_id`; provide an explicit `answers` list and set `rejected=true` with an empty list to decline.
- When a turn is `queued`, `in_progress`, or `result_pending`, call `get_cobuild_turn_status` with the returned current `turn_id`; do not submit a duplicate operation.
- Approve a deletion only when its scope clearly matches the user's stated intent. If it is broader, ambiguous, or surprising, clarify with the user before responding.
- Before triggering a build-affecting prompt, check `./jobs.md` if there's any chance the same flow objects are already mid-build elsewhere — don't kick off overlapping work.
- If Cobuild's coverage can't do what's needed and no read tool covers it either, stop and report the gap rather than falling back to raw `dataikuapi`/Python/REST calls — those aren't available in this environment.
- There is no close or delete conversation tool.
