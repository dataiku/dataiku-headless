# Manifest Section Style — Dataiku Solutions Convention

> The canonical visual style for App Designer / Project Setup section content,
> as used by every Dataiku Solutions reference project. Follow it whenever
> you author a homepage section so the result matches Solutions polish and
> survives upgrades / clone instantiation cleanly.
>
> Companion: `app-designer.md` (manifest schema, tile types, CLI verbs).

---

## Why this doc exists

App Designer manifests can render *any* HTML / markdown a user types into a
section body. Reference Solutions projects all converge on a tight subset:
plain markdown bodies + a small icon palette + standard wiki cross-refs.
Hand-rolling sections with embedded `<h3>`, ad-hoc HTML entities, or
free-form CSS produces output that looks off-brand and breaks when the
project is exported / re-imported / cloned.

This doc lists the working patterns. Stick to them.

---

## Section-level fields

| Field             | Purpose                                                         |
| ----------------- | --------------------------------------------------------------- |
| `sectionTitle`    | Plain-text title rendered as the section header. **Use this.** Do NOT bake the title into the body as an `<h3>`. |
| `sectionText`     | Body content. Markdown + a constrained HTML subset. See below.  |
| `tiles[]`         | Interactive tiles (buttons, dataset edits, dashboard links, …). Tile schema lives in `app-designer.md`. |
| `visibilityCondition` | Optional CEL-like predicate gating section render. See "Collapse / expand". |

A "header-only" section is just `{"sectionTitle": "...", "sectionText": "...", "tiles": []}` —
no special tile type needed.

---

## Body content — markdown over raw HTML

Body text supports markdown. Prefer markdown to inline HTML. The few HTML
escape hatches Solutions projects actually use:

```text
<i class="icon-warning-sign"></i>     # Solutions warning icon
<i class="icon-info-sign"></i>        # Solutions info icon
<i class="icon-ok-sign"></i>          # Solutions success/check icon
<br>                                  # Forced line break inside a paragraph
<b>...</b>                            # When markdown emphasis is unsafe (rare)
```

Anything beyond that — custom `<div>`, inline styles, color spans, table
markup — is brittle. If you find yourself reaching for it, the section is
trying to do too much; split into multiple sections or move the rich content
into a wiki article and link to it.

### Worked example — well-formed section body

```text
**Step 1)** Upload your daily exports as CSV files.

<i class="icon-info-sign"></i> The first column must be the customer ID.
See [the data spec](article:DATA_SPEC) for the full schema.

When uploads are complete, click **Run Pipeline** below.
```

### Worked example — what to avoid

```html
<!-- DO NOT do this -->
<div style="padding:10px;background:#f0f0f0">
  <h3>Step 1) Upload</h3>
  <p>Upload your daily exports&hellip;</p>
</div>
```

The wrapping `<div>` and the inline style do not survive theme changes
and look out of place on the App Designer canvas. The `<h3>` duplicates
what `sectionTitle` already renders.

---

## Cross-references — wiki link syntax

App Designer body text uses the **same `(article:ID)` link syntax as wiki
articles**. Use it for every internal pointer. Identifiers are
case-sensitive and separator-sensitive — `(scenario:Build_All)` and
`(scenario:BUILD_ALL)` are different scenarios.

| Form                       | Renders as                                |
| -------------------------- | ----------------------------------------- |
| `[label](article:ID)`      | Link to wiki article ID                   |
| `[label](scenario:ID)`     | Link to scenario (exact ID, with separators) |
| `[label](dataset:NAME)`    | Link to dataset (exact name, case-sensitive) |
| `[label](dashboard:ID)`    | Link to dashboard                         |
| `[label](folder:ID)`       | Link to managed folder                    |
| `[label](recipe:NAME)`     | Link to recipe                            |

Get the exact ID with the corresponding `dku <noun> list -o json` first;
do not guess by uppercasing or stripping separators. (`BUILDALL` ≠
`Build_All`.)

---

## Collapse / expand sub-blocks — `visibilityCondition`

Solutions Project Setups frequently hide secondary configuration behind a
boolean toggle. The pattern, on a `PROJECT_VARIABLES_EDIT` tile:

```json
{
  "type": "PROJECT_VARIABLES_EDIT",
  "behavior": "INLINE_AUTO_SAVE",
  "params": [
    {
      "name": "show_advanced",
      "type": "BOOLEAN",
      "label": "Show advanced options",
      "defaultValue": false
    },
    {
      "name": "batch_size",
      "type": "INT",
      "label": "Batch size",
      "defaultValue": 1000,
      "visibilityCondition": "model.show_advanced"
    },
    {
      "name": "retry_count",
      "type": "INT",
      "label": "Max retries",
      "defaultValue": 3,
      "visibilityCondition": "model.show_advanced"
    }
  ]
}
```

`visibilityCondition` evaluates against `model.<paramName>`. The expression
language is CEL-like: `model.x`, `model.x && model.y`,
`model.mode == "ADVANCED"`, etc. Always pair the toggle with a
`defaultValue` so the section renders deterministically for new instances.

You can also gate **whole sections** with `visibilityCondition` — same
syntax, on the section dict instead of the param dict — to hide a section
unless a setup variable is set.

---

## Tile-text conventions

When a button or tile prompt needs a verb, Solutions favors plain
imperative voice with no trailing punctuation:

| Bad                          | Good             |
| ---------------------------- | ---------------- |
| `Click here to upload data!` | `Upload data`    |
| `Build now.`                 | `Build pipeline` |
| `Visit Dashboard >>`         | `View dashboard` |

Match the voice to the surrounding section title — if the title is
"Step 1) Upload data", the tile button reads `Upload data`, not
"Click to start".

---

## Recovery — recovering a wiped manifest

If a `set-definition` accidentally wiped the `homepageSections` array
(see CLAUDE.md gotcha on the `PUT {}` foot-gun), Solutions instances
preserve the manifest at clone time. To recover:

```bash
# Find clone instances of the source project
dku project list -o json | jq -r '.[] | select(.key | startswith("ORIG_")) | .key'

# Re-export the manifest from any clone that still has the sections
dku app-designer get -P ORIG_1 -o json > /tmp/manifest.json

# Restore on the source (use --yes --confirm-name because we're "wiping"
# the current empty state to a populated one — guard catches both directions)
dku app-designer set-definition -P ORIG -d @/tmp/manifest.json --yes --confirm-name ORIG
```

Always recover from an instance, not from the source's own export — the
source's export was made *after* the wipe and reflects the empty state.

---

## Quick checklist before saving a manifest

- [ ] `sectionTitle` set — title is NOT inside `sectionText`
- [ ] Body uses markdown; HTML is limited to `<i class="icon-*">`, `<br>`, `<b>`
- [ ] Cross-refs use exact IDs from `dku <noun> list -o json`
- [ ] Toggle params have `defaultValue`
- [ ] `visibilityCondition` references existing param names (`model.<name>`)
- [ ] Tile prompts are imperative, no trailing punctuation
- [ ] If wiping sections, you have `--yes --confirm-name <PROJECT_KEY>` ready

---

## See also

- `app-designer.md` — manifest schema, tile types, CLI verbs, parameter types
- `webapps.md` — for `WEBAPP` tile bindings
- CLAUDE.md § "App-Manifest GET/PUT Asymmetry" — gotcha behind the safety guard
