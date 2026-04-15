# UI Views and Layout

The `uiDefinition` section of a blueprint version controls what users see on the artifact page: how fields are laid out, which view is shown on which workflow step, and any conditional visibility.

## Structure

```json
"uiDefinition": {
  "views": { "<viewId>": <View> },
  "uiStepDefinitions": { "<stepId>": {"viewId": "<viewId>"} },
  "artifactPageViewId": "main"
}
```

| Key | Purpose |
|---|---|
| `views` | Map of view ID → view object. Each view contains a tree of components |
| `uiStepDefinitions` | Map of workflow step ID → which view to show on that step. **Every step in `workflowDefinition.stepDefinitions` must have a matching entry pointing at a real `viewId`** — empty strings render a blank step tab |
| `artifactPageViewId` | The view shown on the artifact's Overview tab (must be a real view id, typically `"main"`) |

## Minimum viable uiDefinition

**Empty `views: {}` does NOT produce default rendering — it produces a BLANK artifact page.** The Govern API silently accepts `"views": {}`, `"artifactPageViewId": ""`, and step `"viewId": ""`, but there is no UI fallback: the page shows nothing, no fields are rendered, and the user sees an empty tab. Every `viewId` reference must resolve to a view that exists in `views{}`.

The minimum viable config defines a single `main` view listing every field, and binds every workflow step and the artifact page to it:

```json
"uiDefinition": {
  "views": {
    "main": {
      "label": "Overview",
      "description": "",
      "viewComponent": {
        "type": "container",
        "layout": {
          "type": "sequential",
          "viewComponents": [
            {"type": "text-field",     "fieldId": "title",      "label": "Title"},
            {"type": "category-field", "fieldId": "risk_level", "label": "Risk level"},
            {"type": "date-field",     "fieldId": "deadline",   "label": "Deadline"}
          ]
        }
      }
    }
  },
  "uiStepDefinitions": {
    "draft":    {"viewId": "main"},
    "review":   {"viewId": "main"},
    "approved": {"viewId": "main"}
  },
  "artifactPageViewId": "main"
}
```

This is the correct starting point when the user hasn't asked for specific layout — one view listing every field, bound to every step. From here you can split into per-step views (see [Common patterns](#common-patterns)) as requirements emerge. Verify after pushing with `dku govern blueprint describe-version BP VER` — the command prints structural warnings for empty views, missing `artifactPageViewId`, unreferenced fields, and other silent-failure patterns.

## View structure

A View has a name, description, and a root viewComponent (a container tree):

```json
"delivery": {
  "label": "Delivery info",
  "description": "",
  "viewComponent": {
    "type": "container",
    "layout": {
      "type": "sequential",
      "viewComponents": [
        { "type": "text-field", "fieldId": "delivery_notes", "label": "Notes" },
        { "type": "uploaded-file-field", "fieldId": "delivery_docs", "label": "Supporting documents" }
      ]
    },
    "label": "",
    "description": "",
    "documentation": ""
  }
}
```

The `viewComponent` is a tree: a container at the root, field/action components as leaves, subcontainers as intermediate nodes.

## Component types

### `container`

Groups child components. Containers can be nested to create sections/subsections.

```json
{
  "type": "container",
  "layout": {
    "type": "sequential",    // or "grid" for multi-column
    "viewComponents": [ ... ]
  },
  "label": "Section title",
  "description": "",
  "documentation": "<p>HTML help text shown below the label</p>"
}
```

Layouts:
- `"type": "sequential"` — vertical stack, one component per row
- `"type": "grid"` — multi-column grid (accepts additional `columns: N` and child-level position hints)

### Field components

One per field type. The `fieldId` references a key in `fieldDefinitions`. These component `type` values are **the full set the Govern server accepts** (derived from a live server `JsonParseException`). Anything not listed is rejected at save time, even if it sounds plausible — `reference-field`, `select-field`, `string-field`, `markdown-field`, and `users-groups-roles-field` all do **NOT** exist.

| Component type | For fieldType |
|---|---|
| `text-field` | TEXT |
| `number-field` | NUMBER |
| `boolean-field` | BOOLEAN |
| `date-field` | DATE |
| `category-field` | CATEGORY |
| `card-reference-field` | REFERENCE — also how USER / GROUP / ROLE are referenced (point at `bp.system.user` / `bp.system.group`) |
| `uploaded-file-field` | UPLOADED_FILE |
| `time-series-field` | TIME_SERIES |
| `table-reference-field` | paired with a table-reference field definition |
| `json-field` | JSON |

Also accepted as view components (non-field, covered separately): `container`, `action`, `plugin-action`.

Common props for all field components:

```json
{
  "type": "text-field",
  "fieldId": "description",
  "label": "Description",
  "description": "Tooltip shown next to the label",
  "documentation": "<p>HTML help shown below</p>",
  "absoluteUiIndex": "<auto-generated uniqueness key>"
}
```

**`absoluteUiIndex`** is auto-generated by the server on first save — it's a stable identifier used for drag-and-drop ordering. You don't need to set it; copy it as-is when round-tripping.

Type-specific props (from the TEXT component's `keepSourceFormat` example):

```json
{
  "type": "text-field",
  "keepSourceFormat": false,   // true = preserves line breaks and whitespace
  "fieldId": "delivery_notes"
}
```

### `action`

Renders a button for a custom action defined in `actions{}`:

```json
{
  "type": "action",
  "actionId": "ac.export_to_pdf",
  "label": "Export"
}
```

An action is **only visible** if some view contains a matching `action` component. An action in `actions{}` but not placed in any view is dead code.

### Conditional components

Any component can have a `conditionalVisibility` clause that hides it based on another field's value:

```json
{
  "type": "text-field",
  "fieldId": "legal_review_notes",
  "conditionalVisibility": {
    "type": "field",
    "fieldId": "needs_legal_review",
    "comparator": "EQUALS",
    "value": true
  }
}
```

## View reuse

Views are shared across UI contexts. A single view can be:
- Bound to one or more workflow steps via `uiStepDefinitions`
- Used as the artifact overview via `artifactPageViewId`
- Referenced as the row view in table displays of governed items

When you update a shared view, every context using it updates automatically. This is why the docs recommend "Create Once, Use Everywhere."

## Common patterns

### One view per workflow step

The simplest non-trivial pattern — each step shows only the fields relevant at that stage:

```json
"views": {
  "exploration": {
    "label": "Exploration",
    "description": "",
    "viewComponent": {
      "type": "container",
      "layout": {"type": "sequential", "viewComponents": [
        {"type": "text-field", "fieldId": "description"},
        {"type": "category-field", "fieldId": "use_case_technical_dimension"},
        {"type": "date-field", "fieldId": "target_end_date"}
      ]}
    }
  },
  "qualification": {
    "label": "Qualification",
    "description": "",
    "viewComponent": {
      "type": "container",
      "layout": {"type": "sequential", "viewComponents": [
        {"type": "category-field", "fieldId": "qualification_risk_rating"},
        {"type": "category-field", "fieldId": "qualification_value_rating"},
        {"type": "text-field", "fieldId": "qualification_value_comments"}
      ]}
    }
  }
},
"uiStepDefinitions": {
  "exploration":    {"viewId": "exploration"},
  "qualification":  {"viewId": "qualification"}
}
```

### Grouped overview

An overview view with grouped subsections:

```json
"main": {
  "label": "Overview",
  "viewComponent": {
    "type": "container",
    "layout": {"type": "sequential", "viewComponents": [
      {
        "type": "container",
        "label": "General information",
        "layout": {"type": "sequential", "viewComponents": [
          {"type": "text-field", "fieldId": "description"},
          {"type": "card-reference-field", "fieldId": "owners"},
          {"type": "date-field", "fieldId": "target_end_date"}
        ]}
      },
      {
        "type": "container",
        "label": "Classification",
        "layout": {"type": "sequential", "viewComponents": [
          {"type": "category-field", "fieldId": "risk_level"},
          {"type": "category-field", "fieldId": "data_sensitivity"}
        ]}
      }
    ]}
  }
}
```

Then bind it via `"artifactPageViewId": "main"`.

## Gotchas

- **Empty `views: {}` ≠ default rendering — it means BLANK artifact page.** The Govern API silently accepts `"views": {}` / `"artifactPageViewId": ""` / step `"viewId": ""`, but the UI has no fallback path: the page renders nothing, no fields are shown. Every `viewId` reference must resolve to a real view in `views{}`. Run `dku govern blueprint describe-version BP VER` after every push — it prints structural warnings for all of these. This is the #1 silent-failure pattern when authoring blueprints and has shipped blank-page blueprints at least once (2026-04-14 `bp.gdpr_data_export`).
- **Every step in `workflowDefinition.stepDefinitions` needs an entry in `uiStepDefinitions`** pointing at a real `viewId`. If you add a step and forget its UI step def — or leave the `viewId` empty — the step's tab renders blank.
- **Field not in any view ≠ field not required.** If a field is marked `required: true` but not placed in any view, users can't set it — and the artifact can't save. Either remove `required: true` or add the field to a view.
- **Dragging and reordering** in the Govern Designer UI mutates `absoluteUiIndex` values. When round-tripping JSON, preserve them to avoid spurious diffs.
- **Conditional visibility conditions are evaluated client-side.** A malformed condition silently fails to match, hiding the component. Test by setting the trigger field to each possible value.
- **Containers can be nested deeply.** There's no hard limit, but readability suffers past 3–4 levels. Prefer multiple sibling containers with clear labels over deep nesting.
- **Table views** (for governed-items tables) are a separate view type — they define the columns shown in artifact listings, not the artifact detail page. Look for views with `analysisDefinition` to identify table views in a round-tripped payload.

## Tip for agents

When editing views, the least-error-prone workflow is:

1. `get-version BP VER -o json > bv.json`
2. Edit only the `uiDefinition.views` portion
3. Leave `absoluteUiIndex` values intact
4. `set-version-definition BP VER --definition @bv.json`
5. Verify in the Govern UI that the page still renders

Do **not** try to hand-author a brand-new view from scratch unless there's no alternative — fork an existing view (e.g. from `bp.system.govern_project/bv.system.default`) and modify it.
