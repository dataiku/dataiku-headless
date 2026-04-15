# Canonical Examples

Real blueprint version payloads that agents can copy-paste-modify instead of authoring from scratch.

## Files

### `starter-version.json`

The smallest sensible blank template. 4 fields (TEXT, REFERENCE, CATEGORY, DATE), 3-step workflow, empty UI views. Use this when the user explicitly asks for a blank template.

Usage:

```bash
# Replace the blueprint ID, then save
jq '.id.blueprintId = "bp.my_bp"' starter-version.json > bv.json
dku govern blueprint create bp.my_bp --definition '{"name": "My Blueprint", "icon": "science"}'
dku govern blueprint create-version bp.my_bp v1
dku govern blueprint set-version-definition bp.my_bp bv.v1 --definition @bv.json
dku govern blueprint set-version-status bp.my_bp bv.v1 ACTIVE
```

### `govern-project-excerpt.json`

Trimmed excerpt of the real `bp.system.govern_project/bv.system.default` payload from a live Govern instance. Contains:

- 6 representative fields: TEXT, DATE, CATEGORY, REFERENCE (list), UPLOADED_FILE (list), CATEGORY (list)
- 5-step workflow (exploration → qualification → progress → rollout → delivery)
- 1 logical hook (computes risk/value scores from category ratings)
- 2 views (delivery, qualification) showing real viewComponent trees
- `hierarchicalParentFieldId` pointing to the business_initiative field

**Use this to understand real-world payload shape** before authoring your own. The `absoluteUiIndex` values in the views are from the live instance — you don't need to set them yourself, but preserving them on round-trip is harmless.

Note the real govern_project has **41 fields** — this excerpt is trimmed for readability. To see the full payload from your own instance:

```bash
dku govern blueprint get-version bp.system.govern_project bv.system.default -o json
```

### `signoff-basic.json`

Minimal working signoff configuration with one user feedback group and one user approver, no recurrence. The `title` is required; everything else uses safe defaults.

Usage:

```bash
# Replace placeholders
sed -i '' 's/REPLACE_WITH_REVIEWER_LOGIN/alice/; s/REPLACE_WITH_APPROVER_LOGIN/bob/' signoff-basic.json
dku govern blueprint create-signoff-config bp.my_bp bv.v1 review --definition @signoff-basic.json
```

**Remember: lowercase `"type": "user"` (or `"group"`, `"role"`, `"global-api-key"`).**

## Forking a system blueprint (the recommended path)

Instead of using `starter-version.json`, fork a system version — you inherit working hooks, reasonable default fields, and tested workflow steps:

```bash
# Fork the system's govern project default
dku govern blueprint create-version bp.my_bp v1 --from bv.system.default --name "v1 of my project"

# The new version inherits everything from bv.system.default
dku govern blueprint get-version bp.my_bp bv.v1 -o json > bv.json

# Edit and save back
$EDITOR bv.json
dku govern blueprint set-version-definition bp.my_bp bv.v1 --definition @bv.json
dku govern blueprint set-version-status bp.my_bp bv.v1 ACTIVE
```

This is **always** the preferred starting point unless the user specifically asks for a blank template.
