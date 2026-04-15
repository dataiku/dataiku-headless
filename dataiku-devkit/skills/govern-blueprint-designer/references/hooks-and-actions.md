# Logical Hooks and Custom Actions

Both are Python scripts attached to a blueprint version. **Hooks** fire automatically on artifact lifecycle events. **Actions** are buttons users explicitly trigger from the artifact page.

## Logical hooks

### Shape

```json
"logicalHookList": [
  {
    "name": "Compute risk score",
    "description": "Derive risk_score from risk_level",
    "phases": ["CREATE", "UPDATE"],
    "script": "from govern.core.handler import get_handler\n..."
  }
]
```

| Key | Type | Purpose |
|---|---|---|
| `name` | string | Human-readable hook name |
| `description` | string | Inline description |
| `phases` | array of strings | When the hook fires. Values: `"CREATE"`, `"UPDATE"`, `"DELETE"` |
| `script` | string | Python source. Runs in a Govern-specific interpreter |

`phases` is a set — include each phase the hook should fire on. Most business-logic hooks use `["CREATE", "UPDATE"]`.

### Handler API

The hook script accesses the artifact and context through a `handler` object:

```python
from govern.core.handler import get_handler

handler = get_handler()
artifact = handler.artifact          # the artifact being saved/created/deleted
phase = handler.hookPhase             # "CREATE", "UPDATE", or "DELETE"

# Read fields
risk = artifact.fields.get("risk_level")

# Write fields (flow back into the saved artifact)
artifact.fields["risk_score"] = 80 if risk == "High" else 20

# Schedule UPDATE hooks on neighbor artifacts AFTER this action commits
handler.artifactIdsToUpdate.append("ar.123")
```

**Do NOT use the dataikuapi client to mutate neighbors.** The official Govern docs warning:

> Hooks are executed before the actual action is committed, which means that the item action (save/create/delete) may fail after the hook is run. For this reason, it is not recommended to have external side-effects on other items such as using the API client to save/create/delete an item in Govern because there may be inconsistent results.
>
> In addition, saving/creating/deleting an external item via the API client may also trigger another hook execution which is not supported at the moment and will fail the action.
>
> If there is a need to trigger a hook on a neighbor item for syncing reasons (ie. compute a sum from children items), you may fill the `handler.artifactIdsToUpdate` list with artifacts IDs to schedule the execution of their UPDATE hooks after the action has completed on the initial artifact.

### Failure handling

If the hook raises or sets a failure marker, the initial artifact action **fails** and is rolled back. This is the prescribed way to block invalid state:

```python
handler = get_handler()
risk = handler.artifact.fields.get("risk_level")
if risk == "High" and not handler.artifact.fields.get("final_approvers"):
    handler.fail("High-risk artifacts must have Final approvers assigned before save")
```

(Exact failure API — `handler.fail(msg)` vs raising — varies by Govern version. Check with `get-version` output of an existing blueprint that has failure-handling hooks.)

### Live example: risk score computation

From `bp.system.govern_project/bv.system.default`:

```python
from govern.core.handler import get_handler

def map_category(cat):
    x = cat.lower()
    return {'low': 20, 'medium low': 40, 'medium high': 60, 'high': 80}[x]

handler = get_handler()
hookPhase = handler.hookPhase
artifact = handler.artifact

risk_rating = artifact.fields.get('qualification_risk_rating')
value_rating = artifact.fields.get('qualification_value_rating')

if risk_rating is not None:
    artifact.fields['qualification_risk_score'] = 100 - map_category(risk_rating)
else:
    artifact.fields['qualification_risk_score'] = None

if value_rating is not None:
    artifact.fields['qualification_value_score'] = map_category(value_rating)
else:
    artifact.fields['qualification_value_score'] = None
```

This hook fires on CREATE and UPDATE, reads two CATEGORY fields, and writes two NUMBER fields.

### Hook common patterns

| Goal | Pattern |
|---|---|
| Auto-populate a field from another | `artifact.fields["derived"] = f(artifact.fields.get("source"))` |
| Block save on invalid state | `handler.fail("reason")` |
| Sync a parent aggregate | `handler.artifactIdsToUpdate.append(parent_id)` + parent has its own hook |
| Stamp created-by / created-at | On CREATE only, set user/date fields from `handler.authCtx.login` |
| Read a REFERENCE field's target | `target = handler.client.get_artifact(artifact.fields["owner"])` — but only for READ, never write |

## Custom actions

### Shape

```json
"actions": {
  "ac.export_to_pdf": {
    "name": "Export to PDF",
    "description": "Generate a PDF report of the artifact",
    "script": "from govern.core.handler import get_handler\n..."
  }
}
```

Actions are a **dict** keyed on action ID (`ac.<identifier>`), not a list. The key is permanent once created.

| Key | Type | Purpose |
|---|---|---|
| `name` | string | Button label shown on the artifact page |
| `description` | string | Tooltip / help text |
| `script` | string | Python source that runs when the button is clicked |

The action is only visible if it's placed inside a view's viewComponent (see [ui-views.md](ui-views.md)). An action defined in `actions{}` but not referenced in any view is never shown.

### Action handler API

```python
from govern.core.handler import get_handler

handler = get_handler()
artifact = handler.artifact
user = handler.authCtx                # who clicked the button
params = handler.parameters           # optional action parameters (if defined)

# Log (shows in action execution history)
handler.log("Starting PDF export...")

# Fail with a user-visible error
if not artifact.fields.get("description"):
    handler.fail("Cannot export: description is empty")

# Success — any fields written to artifact.fields are saved
artifact.fields["last_exported_at"] = handler.now()
```

Unlike hooks, actions **can** safely call `dataikuapi` clients for side effects — they're explicit user-triggered operations, not lifecycle event handlers.

### Action gotchas

- **IDs are `ac.<identifier>` and permanent** once saved. Rename is impossible via API — create a new action and remove the old one.
- **Actions need to be placed in a view** to be visible. Define the action in `actions{}` then add a view component with `"type": "action", "actionId": "ac.your_id"` in the relevant view.
- **Script errors show only in the UI's action history** — debug by clicking the button once and inspecting the returned error, or adding `handler.log(...)` calls.
- **No sandbox enforcement.** Actions have full `dataikuapi` access as the user who clicked. Treat them with the same care as any server-side script.

## When to use hooks vs actions vs visual workflow

| Use case | Mechanism |
|---|---|
| Derive a field value from others | Hook on CREATE/UPDATE |
| Block save on invalid state | Hook on CREATE/UPDATE with `handler.fail()` |
| Send an email when an artifact is approved | Hook on UPDATE that watches `workflow.steps.<step>.status` |
| Generate a report on demand | **Action** (user-triggered, may be slow or external) |
| Move an artifact to a specific step | **Action** (user chooses to do it) |
| Cascade updates to children | Hook with `handler.artifactIdsToUpdate` |
| Integrate with an external ticket system | Hook for fire-and-forget events, Action for user-triggered creation |

## Debugging hooks and actions

- **Print is fine.** Hooks and actions support `print()` — output shows in DSS backend logs (`~/dip/caches/logs/backend.log`) during execution.
- **Failures surface as artifact save errors.** If a hook raises, the entire save is rolled back and the UI shows the exception message.
- **Use `get-version BP VER -o json`** to inspect the current script without opening the Govern Designer UI.
- **Test iteratively**: update a hook, create a test artifact, inspect the result, repeat. Don't try to get a complex hook right in one save.
- **Version carefully.** Changing a hook on an ACTIVE version affects **future** events only — existing artifacts don't retroactively re-run CREATE hooks.
