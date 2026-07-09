---
name: projects
description: Explore, create, and edit Dataiku projects through MCP tools. Use when an agent must list projects, inspect the flow, or read/write project metadata (description, tags, checklists) and project variables.
---

# Project Operations

## Workflow

- Use `list_projects` to discover and confirm the exact `project_key`. Never invent project keys.
- For flow orientation: `get_flow_items_in_traversal_order`. Supplement with `list_recipes`, `list_datasets`, `list_managed_folders`, `list_saved_models`, or `list_agents` as needed for the task.
- `set_project_metadata` and `set_project_variables` are full replaces — always call the corresponding get tool first, modify only what you need, then pass the complete dict back.
- `set_project_metadata` requires **project admin** privileges. If it returns `Action forbidden`, inform the user and do not retry.
- Project creation (`create_project`) is significant — confirm the project key and name with the user before calling.

## Project Metadata

**Display name field:** use `name` when creating a project; use `label` when reading or updating an existing project's metadata.

`get_project_metadata` returns the full metadata dict. Key editable fields:

| Field | Type | Description |
| --- | --- | --- |
| `label` | string | Project display name |
| `shortDesc` | string | One-line description shown in the project list |
| `description` | string | Long-form markdown description |
| `tags` | list of strings | Project tags |
| `checklists` | list of checklist objects | Project to-do lists |

### Checklist structure

The `checklists` field is double-nested — the outer key is a wrapper, the inner key holds the array:

```json
{
  "checklists": {
    "checklists": [
      {
        "title": "Pre-launch checks",
        "createdOn": 0,
        "items": [
          {"text": "Validate training data", "done": false, "createdOn": 0, "createdBy": "user", "stateChangedOn": 0},
          {"text": "Review model metrics", "done": true, "createdOn": 0, "createdBy": "user", "stateChangedOn": 0}
        ]
      }
    ]
  }
}
```

Preserve all item fields (`createdOn`, `createdBy`, `stateChangedOn`) when round-tripping — only modify `done` or `text`.

## Project Variables

`get_project_variables` returns `{"standard": {...}, "local": {...}}`.

- **standard**: shared across all instances running the project
- **local**: instance-specific overrides

## Flow Zones

Flow zones group related flow items visually.

1. `list_flow_zones` — see existing zones and their contents (`zone_id`, `name`, `items`).
2. `get_flow_items_in_traversal_order` — see all item refs and types.
3. `add_items_to_flow_zone` with target `zone_id` and a list of `{object_type, object_id}` pairs. Items are automatically removed from their current zone. DSS may auto-move dependents (e.g. moving a saved model pulls its training recipe) — check `list_flow_zones` after.
4. To move items back to the default zone: use `zone_id='default'`.
5. `create_flow_zone` with a name and optional hex color to create a new zone.

**Default zone is virtual.** Its `items` from `list_flow_zones` is always `[]` — even after `add_items_to_flow_zone(zone_id='default', ...)` (that call only removes items from non-default zones; it does not populate a stored list). Default contains every flow item not explicitly placed in another zone. If no non-default zones exist, `list_flow_zones` may return `zone_count: 0`; treat that as "all items are in Default." To enumerate Default's contents, cross-reference `get_flow_items_in_traversal_order` against the union of items across non-default zones.

**`object_type` values** (use the ref from `get_flow_items_in_traversal_order` as `object_id`):

| Flow item type | `object_type` to pass |
| --- | --- |
| `COMPUTABLE_DATASET` | `DATASET` |
| `RUNNABLE_RECIPE` | `RECIPE` |
| `COMPUTABLE_FOLDER` | `MANAGED_FOLDER` |
| `COMPUTABLE_SAVED_MODEL` | `SAVED_MODEL` |
| `COMPUTABLE_RETRIEVABLE_KNOWLEDGE` | `RETRIEVABLE_KNOWLEDGE` |
| `COMPUTABLE_MODEL_EVALUATION_STORE` | `MODEL_EVALUATION_STORE` |

`RUNNABLE_IMPLICIT_RECIPE` items cannot be moved directly — they follow their associated saved model automatically.
