---
name: dataiku-recipe-shell
description: "Run shell scripts in DSS for automation tasks."
---

# shell Recipe Skill

Use this skill with `recipes` for work focused on recipe type `shell`.

## I/O Requirements

**Inputs:** any combination of datasets and managed folders (0 or more, all role `main`).

**Outputs:** any combination of datasets and managed folders (1 or more, all role `main`).

## Type-Specific Update Notes

Use parent rules from `dataiku-skills/recipes/SKILL.md` section `Settings And Payload Update Rules`.

- Keep updates minimal and use the action that matches recipe family (`set_payload` for most visual recipes, `set_code` for code recipes).
- Use `set_inputs` and `set_outputs` for input/output changes (not payload/params).

## DSS Reference

- Reference: `Shell recipes` (https://doc.dataiku.com/dss/latest/code_recipes/shell.html)
