---
name: dataiku-recipe-r
description: "Write R recipes with DSS dataset and managed-folder flow I/O."
---

# r Recipe Skill

Use this skill with `recipes` for work focused on recipe type `r`.

## I/O Requirements

**Inputs:** any combination of datasets and managed folders (0 or more, all role `main`).

**Outputs:** any combination of datasets and managed folders (1 or more, all role `main`).

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- Keep updates minimal and use the action that matches recipe family (`set_payload` for most visual recipes, `set_code` for code recipes).
- Use `set_inputs` and `set_outputs` for input/output changes (not payload/params).

## DSS Reference

- Reference: `R recipes` (https://doc.dataiku.com/dss/latest/code_recipes/r.html)
