---
name: dataiku-recipe-python
description: "Write Python recipes with flexible DSS flow I/O, including datasets, folders, model refs, knowledge banks, and evaluation stores."
---

# python Recipe Skill

Use this skill with `recipes` for work focused on recipe type `python`.

## I/O Requirements

**Inputs:** any combination of datasets, managed folders, saved models, Knowledge Banks, and evaluation stores (0 or more, all role `main`).

**Outputs:** any combination of datasets, managed folders, Knowledge Banks, evaluation stores, and MLFlow `MLFLOW_PYFUNC` saved models (1 or more, all role `main`). Other saved model families can be inputs but not outputs.

## Visual-First Check

Only build a Python recipe if the user explicitly requested it; there is not other valid justification. If a Python recipe was not requested, follow the parent `recipes` skill's visual-first recipe-family selection protocol.

When creating a Python recipe, `create_recipe` requires a non-empty `code_recipe_justification` describing the reason for using code. The only valid justification is that the user explicitly requested code.

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- Keep updates minimal and use the action that matches recipe family (`set_payload` for most visual recipes, `set_code` for code recipes).
- Use `set_inputs` and `set_outputs` for input/output changes (not payload/params).

## DSS Reference

- Reference: `Python recipes` (https://doc.dataiku.com/dss/latest/code_recipes/python.html)
