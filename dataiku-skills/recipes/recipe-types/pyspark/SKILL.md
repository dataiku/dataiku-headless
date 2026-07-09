---
name: dataiku-recipe-pyspark
description: "Write Spark recipes in Python using the PySpark API."
---

# pyspark Recipe Skill

Use this skill with `recipes` for work focused on recipe type `pyspark`.

## I/O Requirements

**Inputs:** any combination of datasets and managed folders (0 or more, all role `main`).

**Outputs:** any combination of datasets and managed folders (1 or more, all role `main`).

All inputs and outputs must live on connections accessible to the configured Spark cluster (typically HDFS, S3, GCS, Azure Blob, or other object-storage/distributed-filesystem backends).

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- Keep updates minimal and use the action that matches recipe family (`set_payload` for most visual recipes, `set_code` for code recipes).
- Use `set_inputs` and `set_outputs` for input/output changes (not payload/params).

## DSS Reference

- Reference: `PySpark recipes` (https://doc.dataiku.com/dss/latest/code_recipes/pyspark.html)
