---
name: cobuild
description: Use Dataiku Cobuild for project-level asset creation, modification, and conversational co-development. Use when an agent needs to build or change project assets, continue a Cobuild conversation, or gather project context before making changes.
---

# Cobuild

Cobuild is Dataiku's AI building agent for co-developing Dataiku projects. It can build and modify flows, recipes, models, dashboards, webapps, notebooks, wiki content, agents, scenarios, and other project assets through a retained conversation.

Use this skill as the default path for project-level asset creation. This includes both broad requests such as "build me a flow for this use case" and narrow requests such as "create a filter recipe on dataset X".

## Cobuild Concepts

- A Cobuild conversation is stateful and bound to one project. Reuse its `conversation_id` for related work in that project.
- Conversations and retained turns are **process-local**: they live only in the running MCP server process. A server restart drops them, so start a new conversation rather than reusing an old `conversation_id`.
- `allow_edit_project` determines whether Cobuild may modify project assets. Use `false` for inspection or explanation and `true` only for an explicitly requested creation or modification.
- One turn can run for minutes. If a call returns `timeout` or `in_progress`, its worker is still running: poll the returned `turn_id` with `get_cobuild_turn_status`. **Never resend a timed-out instruction** — the original worker is authoritative and a resend can duplicate a mutation.
- Only one turn runs per conversation at a time. A send while a turn is in flight returns `busy` with that turn's `turn_id`; poll it instead of resending.
- Cobuild can inspect project context, propose changes, and make permitted changes through the same conversation.
- Deletion is a separate confirmation step. A request to edit does not authorize a broader or unexpected deletion.

## When To Use This Skill

Use this skill when the user wants to:

- create project assets
- modify project assets through a conversational workflow
- have Cobuild inspect a project and then build or refactor something
- continue an existing Cobuild conversation

Do not use this skill when:

- the task is inspection-only and a direct read tool is the simpler path
- the task is not a project-level Cobuild workflow

## Workflow

1. Confirm the exact `project_key`.
2. When changing an existing asset, inspect it through its relevant object skill before preparing the Cobuild request. For greenfield work, ask Cobuild to inspect the necessary project context.
3. Reuse a known `conversation_id` only with its matching `project_key`. For a requested continuation without an available ID, use `list_cobuild_conversations` to rediscover it.
4. Start a conversation with `start_cobuild_conversation` only when no existing conversation applies.
5. Send the grounded request with `conversation_id` and `project_key`. Set `allow_edit_project=false` for inspection or explanation and `true` for an explicitly requested creation or modification.
6. If the call returns `timeout`, `in_progress`, or `busy`, retain its `turn_id` and poll `get_cobuild_turn_status`. Do not resend the instruction: the original worker is still authoritative.
7. Retain the returned `conversation_id` for follow-up work.
8. If Cobuild returns `needs_confirmation`, inspect the complete `objects_to_delete` and `deletion_impacts`, then pass its exact `confirmation_id` to `answer_cobuild_confirmation` with `APPROVE` or `CANCEL`.
9. After a build, verify saved settings through independent read tools and run `audit_project` as a finish gate (not a proof of correctness). Pass an output contract when the delegated request named required datasets, columns, types, row minima, or sampled non-blank fields. Treat reviewability warnings as advice, not proof that the build is wrong.

## Prompt Guidance

- Prefer explicit Dataiku object names in prompts.
- For creation requests, describe the intended asset, inputs, outputs, and constraints clearly.
- If Cobuild needs project context, mention the relevant datasets, recipes, folders, models, dashboards, or other assets directly by name.
- For existing assets, include the configuration and constraints discovered through the relevant object skill.

## Preferred Tools

| Goal | Tool |
| --- | --- |
| Start a new Cobuild conversation for a project | `start_cobuild_conversation` |
| Continue a Cobuild conversation | `send_cobuild_message` |
| Poll a long-running or timed-out turn | `get_cobuild_turn_status` |
| Approve or cancel a Cobuild delete confirmation request | `answer_cobuild_confirmation` |
| Rediscover retained conversations for a project | `list_cobuild_conversations` |
| Review Flow evidence and an explicit output contract | `audit_project` |

## Safety Rules

- Keep each `conversation_id` paired with its matching `project_key`.
- Use `allow_edit_project=true` only when the user has explicitly requested a creation or modification.
- A `timeout` ends only the MCP client's wait, not the worker. Poll the returned `turn_id` with `get_cobuild_turn_status`; never resend a timed-out mutation.
- Treat `transport_outcome_unknown` as ambiguous. Inspect project state before deciding whether to retry any mutation.
- Conversations and turns do not survive a server restart. If a `turn_id` or `conversation_id` is reported unknown, start a new conversation rather than resending.
- `send_cobuild_message` may return `needs_confirmation`, with the exact proposal in `objects_to_delete` and `deletion_impacts`.
- Approve a deletion only when its scope clearly matches the user's stated intent. If it is broader, ambiguous, or surprising, clarify with the user before responding.
- Before triggering a build-affecting prompt, check `../jobs/SKILL.md` if there's any chance the same flow objects are already mid-build elsewhere — don't kick off overlapping work.
- If Cobuild's coverage can't do what's needed and no read tool covers it either, stop and report the gap rather than falling back to raw `dataikuapi`/Python/REST calls — those aren't available in this environment.
- There is no close or delete conversation tool.
- `audit_project` covers datasets, recipes, zones, cached counts, bounded samples, wiki presence, and DSS Flow consistency. Only FAIL-severity checks (Flow consistency and an explicit contract) block; documentation and layout are advisory. It does not certify scenarios, connections, models, code environments, or live application behavior.
