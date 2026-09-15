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
- Cobuild availability = instance+user gate. `get_cobuild_status` checks it before any conversation. `enabled=true` covers those credentials; LLM backend and project permissions stay unproven.
- Every Cobuild payload carries `project_url`, the Dataiku UI URL of the conversation's project on the instance that conversation is pinned to. Dataiku exposes no per-conversation URL: Cobuild opens as a panel inside the project, so `project_url` points at the project and the user opens Cobuild from there.

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
6. A message, confirmation answer, or question answer waits for up to 240 seconds by default. If it returns `status=queued` or `status=in_progress`, keep calling `get_cobuild_turn_status` with its exact `turn_id` until it returns a terminal result; never resend the instruction. Cobuild has a finite server-side timeout, so this polling does not continue indefinitely.
7. If an interrupted call loses its response, use `list_cobuild_conversations` to recover the conversation's `current_turn_id`. When it is present, call `get_cobuild_turn_status` before doing anything else; when it is absent, a new message may be sent.
8. Independent work may continue while a turn is pending. Retain its `conversation_id` and `turn_id`, then poll again after each bounded unit of independent work and before any dependent action or completion report.
9. Retain the returned `conversation_id` for follow-up work.
10. If Cobuild returns a delete confirmation request, call `get_cobuild_turn_status` with its exact `turn_id`, inspect the retained deletion details, then use `answer_cobuild_confirmation`.
11. If Cobuild returns a question request, call `get_cobuild_turn_status` with its exact `turn_id`, then inspect its retained `question` object before using `answer_cobuild_question`.
12. If an answer returns "No pending question/confirmation found," do not retry. Inspect the project or UI state, then continue the same conversation with a new message if appropriate.

## Prompt Guidance

- Unless the user explicitly requests otherwise, keep each turn to one coherent unit of work. For example, creating a recipe, adding descriptions to a number of objects, editing a Wiki. The intention here is to not submit large, monolithic instructions to Cobuild that cover many actions at once.
- Large transformations may hit Cobuild's server-side time cap and end mid-turn. After a timed-out turn, inspect the project to see what was actually created, then re-issue instructions covering only the remaining work.
- Prefer explicit Dataiku object names in prompts.
- For creation requests, describe the intended asset, inputs, outputs, and constraints clearly.
- If Cobuild needs project context, mention the relevant datasets, recipes, folders, models, dashboards, or other assets directly by name.
- For existing assets, include the configuration and constraints discovered through the relevant guide.

## Preferred Tools

| Goal | Tool |
| --- | --- |
| Check Cobuild availability | `get_cobuild_status` |
| Start a new Cobuild conversation for a project | `start_cobuild_conversation` |
| Continue a Cobuild conversation | `send_cobuild_message` |
| Approve or cancel a Cobuild delete confirmation request | `answer_cobuild_confirmation` |
| Answer a Cobuild question request | `answer_cobuild_question` |
| Wait for or recover a retained Cobuild operation | `get_cobuild_turn_status` |
| Rediscover retained conversations for a project | `list_cobuild_conversations` |

## Safety Rules

- Keep each `conversation_id` paired with its matching `project_key`.
- Use `allow_edit_project=true` only when the user has explicitly requested a creation or modification.
- `send_cobuild_message` defaults `allow_edit_project` to `false`.
- A terminal turn may return `is_confirmation_request=true`, with deletion details in `objects_to_delete` and `deletion_impacts`, or `is_question_request=true`, with answer constraints in `question`.
- Treat `project_url` as an optional link for viewing the conversation in Dataiku. Surface it when the user asks to inspect or continue the conversation in the UI.
- Before answering a confirmation or question, always retrieve and inspect its exact current `turn_id` with `get_cobuild_turn_status`.
- Answer confirmations only with the exact current `turn_id`. Old, duplicate, and mismatched turn IDs are rejected.
- Answer questions only with their exact current `turn_id` and an explicit `answers` list. Use `answers=[]` with `rejected=true` to decline.
- When `rejected=true`, `answers` must be empty.
- Cobuild conversations can continue concurrently in the Dataiku UI and through MCP/API. A question or deletion confirmation is a single Dataiku-side action; the first channel to answer consumes it.
- If an MCP answer returns "No pending question/confirmation found," it may have been answered in the UI or invalidated server-side. Do not retry; inspect the project or UI state, then continue the same conversation with a new message if appropriate.
- Answer a question only when the user request or inspected context determines the answer. Otherwise, ask the user.
- Honor `question.allow_multiple_answers` and `question.allow_custom_answer`; set `used_custom_answer=true` when supplying a custom free-text answer.
- When a turn is `queued` or `in_progress`, retain its exact IDs and continue polling until its terminal result. Independent work is allowed, but do not send another message in the same conversation, take an action that depends on the turn succeeding, or report the relevant Cobuild work complete while it remains pending.
- Approve a deletion only when its scope clearly matches the user's stated intent. If it is broader, ambiguous, or surprising, clarify with the user before responding.
- Before triggering a build-affecting prompt, check `./jobs.md` if there's any chance the same flow objects are already mid-build elsewhere — don't kick off overlapping work.
- If Cobuild cannot perform the request and no direct tool covers it, stop and report the gap. Include the Dataiku version when known, but attribute the gap to that version only when the requirement is established; otherwise, do not guess or fall back to raw APIs.
- `get_cobuild_status` probes by opening a conversation. Leaves one permanent "Empty chat" in the probed project, visible to the probing account alone, removable by hand in its Cobuild panel. Pass a `project_key` the user owns.
- There is no close or delete conversation tool.
