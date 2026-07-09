---
name: cobuild
description: Use Dataiku Cobuild as the default path for project-level asset creation and conversational project co-development. Cobuild can inspect a project, propose changes, create or modify assets when allowed, and request confirmation before destructive actions.
---

# Cobuild

Cobuild is Dataiku's AI building agent for co-developing DSS projects. It can build and modify flows, recipes, models, dashboards, webapps, notebooks, wiki content, agents, scenarios, and other project assets through a retained conversation.

Use this skill as the default path for project-level asset creation. This includes both broad requests such as "build me a flow for this use case" and narrow requests such as "create a filter recipe on dataset X".

## When To Use This Skill

Use this skill when the user wants to:
- create project assets
- modify project assets through a conversational workflow
- have Cobuild inspect a project and then build or refactor something
- continue an existing Cobuild conversation

Do not use this skill when:
- the task is inspection-only and a direct read tool is the simpler path
- the task is not a project-level Cobuild workflow

## Execution Pattern

1. Confirm the exact `project_key`.
2. Start a conversation with `start_cobuild_conversation`.
3. Retain and reuse the returned `conversation_id`.
4. Send follow-up prompts with both `conversation_id` and `project_key`.
5. For creation or modification requests, use `allow_edit_project=true`.
6. If Cobuild returns a delete confirmation request, inspect the returned deletion details and continue through `answer_cobuild_confirmation`.
7. Use `list_cobuild_conversations(project_key=...)` when you need to rediscover a retained conversation for the current project.

## Prompt Guidance

- Prefer explicit DSS object names in prompts.
- For creation requests, describe the intended asset, inputs, outputs, and constraints clearly.
- For inspection or explanation prompts, use `allow_edit_project=false`.
- For creation or modification prompts, use `allow_edit_project=true`.
- If Cobuild needs project context, mention the relevant datasets, recipes, folders, models, dashboards, or other assets directly by name.

## Preferred Tools

| Goal | Tool |
| --- | --- |
| Start a new Cobuild conversation for a project | `start_cobuild_conversation` |
| Continue a Cobuild conversation | `send_cobuild_message` |
| Approve or cancel a Cobuild delete confirmation request | `answer_cobuild_confirmation` |
| Rediscover retained conversations for a project | `list_cobuild_conversations` |

## Confirmation Behavior

- `send_cobuild_message` may return `is_confirmation_request=true`.
- Confirmation requests include deletion details in `objects_to_delete` and `deletion_impacts`.
- Continue the flow with `answer_cobuild_confirmation`.
- If the requested deletion clearly matches the user's stated intent, the agent may send `APPROVE`.
- If the deletion scope is broader than the user's request, ambiguous, or otherwise surprising, stop and clarify before approving.

## Key Behaviors And Limits

- Cobuild is conversational and stateful. Reuse the same `conversation_id` across related steps.
- `conversation_id` reuse is project-specific. Always pass the matching `project_key`.
- Cobuild can inspect and describe existing assets, but this skill should be the default route when the task includes creating project assets.
- Do not assume Cobuild has richer UI context than what the MCP tool flow provides. Be explicit in prompts.
- There is no close/delete conversation tool.
