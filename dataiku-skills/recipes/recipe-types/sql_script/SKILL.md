---
name: dataiku-recipe-sql_script
description: "Use SQL Script recipes for multi-statement SQL workflows when Query mode is insufficient."
---

# sql_script Recipe Skill

Use this skill with `recipes` for work focused on recipe type `sql_script`.

## I/O Requirements

**Inputs (all role `main`):** 0 or more datasets — referenced in the SQL script by their DSS names.

**Outputs (all role `main`):** 0 or more datasets — each populated by a corresponding statement in the script.

All inputs and outputs must live on the **same SQL connection** (category `sql_dbs`). Use `list_connections(connection_category="sql_dbs")` to discover available SQL connections before creating or wiring datasets.

## Referencing Datasets in SQL Code

Use `${tbl:DATASET_NAME}` to reference a DSS dataset as its physical SQL table identifier (fully-qualified across schemas/databases). Raw table names and DSS variable syntax (`${DATASET_NAME}`) do not resolve correctly across schema boundaries.

```sql
-- Correct
SELECT * FROM ${tbl:MY_INPUT_DATASET} WHERE "STATUS" = 'active'

-- Wrong — raw name or variable syntax will fail if schemas differ
SELECT * FROM MY_INPUT_DATASET ...
SELECT * FROM ${MY_INPUT_DATASET} ...
```

For output datasets in sql_script, the physical table does not pre-exist before the first run. Use `CREATE OR REPLACE TABLE` (or equivalent DDL for your database) rather than `INSERT INTO`:

```sql
CREATE OR REPLACE TABLE ${tbl:MY_OUTPUT_DATASET} AS
SELECT ... FROM ${tbl:MY_INPUT_DATASET};
```

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- Keep updates minimal and use the action that matches recipe family (`set_payload` for most visual recipes, `set_code` for code recipes).
- Use `set_inputs` and `set_outputs` for input/output changes (not payload/params).

## DSS Reference

- Reference: `SQL recipes` (https://doc.dataiku.com/dss/latest/code_recipes/sql.html)
