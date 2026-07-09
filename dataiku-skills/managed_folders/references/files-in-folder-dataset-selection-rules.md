---
name: files-in-folder-dataset-selection-rules-reference
description: "Shape and examples for the filesSelectionRules object used in create_files_in_folder_dataset."
---

# Files Selection Rules

Controls which files inside a managed folder a `FilesInFolder` dataset reads.

## Modes

| `mode` | Reads |
|--------|-------|
| `ALL_FILES` | Every file in the folder (default when omitted) |
| `EXPLICIT_SELECT_FILES` | Only the files listed in `explicitFiles` |
| `RULES_INCLUDED_ONLY` | Only files matching at least one rule in `includeRules` |
| `RULES_ALL_BUT_EXCLUDED` | All files except those matching a rule in `excludeRules` |

## Rule Object Shape

```json
{
  "matchingMode": "FILENAME",
  "mode": "GLOB",
  "expr": "*.csv"
}
```

| Field | Values |
|-------|--------|
| `matchingMode` | `"FILENAME"` — match on the filename only; `"FULL_PATH"` — match on the full path within the folder |
| `mode` | `"GLOB"` or `"REGEXP"` |
| `expr` | The glob pattern or regular expression |

## Examples

**Single explicit file:**
```json
{
  "mode": "EXPLICIT_SELECT_FILES",
  "explicitFiles": ["jan.csv"],
  "includeRules": [],
  "excludeRules": []
}
```

**All CSVs in the folder:**
```json
{
  "mode": "RULES_INCLUDED_ONLY",
  "includeRules": [{"matchingMode": "FILENAME", "mode": "GLOB", "expr": "*.csv"}],
  "explicitFiles": [],
  "excludeRules": []
}
```

**All files except a specific one:**
```json
{
  "mode": "RULES_ALL_BUT_EXCLUDED",
  "excludeRules": [{"matchingMode": "FILENAME", "mode": "GLOB", "expr": "archive.csv"}],
  "explicitFiles": [],
  "includeRules": []
}
```
