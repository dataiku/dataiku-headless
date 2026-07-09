---
name: dataiku-recipe-sql_query
description: "Use SQL Query recipes for SELECT-based transformations with DSS-managed output plumbing."
---

# sql_query Recipe Skill

Use this skill with `recipes` for work focused on recipe type `sql_query`.

## I/O Requirements

**Inputs (all role `main`):** 0 or more datasets — referenced in the SQL query by their DSS names.

**Output:** exactly 1 dataset (role `main`) — populated by the SELECT result.

All inputs and the output must live on the **same SQL connection** (category `sql_dbs`). Use `list_connections(connection_category="sql_dbs")` to discover available SQL connections before creating or wiring datasets.

## Referencing Datasets in SQL Code

Use `${tbl:DATASET_NAME}` to reference a DSS dataset as its physical SQL table identifier (fully-qualified across schemas/databases). Raw table names and DSS variable syntax (`${DATASET_NAME}`) do not resolve correctly across schema boundaries.

```sql
-- Correct
SELECT * FROM ${tbl:MY_INPUT_DATASET} WHERE "AMOUNT" > 1000

-- Wrong — raw name or variable syntax will fail if schemas differ
SELECT * FROM MY_INPUT_DATASET ...
SELECT * FROM ${MY_INPUT_DATASET} ...
```

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- Keep updates minimal and use the action that matches recipe family (`set_payload` for most visual recipes, `set_code` for code recipes).
- Use `set_inputs` and `set_outputs` for input/output changes (not payload/params).

## DSS Reference

- Reference: `SQL recipes` (https://doc.dataiku.com/dss/latest/code_recipes/sql.html)
