---
name: dataiku-recipe-spark_sql_query
description: "Populate outputs with SparkSQL queries over input datasets."
---

# spark_sql_query Recipe Skill

Use this skill with `recipes` for work focused on recipe type `spark_sql_query`.

## I/O Requirements

**Inputs (all role `main`):** 0 or more datasets — referenced in the SparkSQL query by their DSS names.

**Output:** exactly 1 dataset (role `main`) — populated by the query result.

All inputs and the output must live on connections accessible to the configured Spark cluster (typically HDFS, S3, GCS, Azure Blob, or other object-storage/distributed-filesystem backends).

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- Keep updates minimal and use the action that matches recipe family (`set_payload` for most visual recipes, `set_code` for code recipes).
- Use `set_inputs` and `set_outputs` for input/output changes (not payload/params).

## DSS Reference

- Reference: `SparkSQL recipes` (https://doc.dataiku.com/dss/latest/code_recipes/sparksql.html)
