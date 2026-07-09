---
name: dataiku-recipe-spark_scala
description: "Write Spark recipes in Scala with Spark-native dataset processing."
---

# spark_scala Recipe Skill

**Not supported via MCP.** Stop and report this limitation to the user — do not attempt to create, configure, or run `spark_scala` recipes through MCP tools.

## Why

Spark Scala recipes must be compiled before they can run. Compilation is only triggered by the DSS UI (save action in the recipe editor). Even if code is written with `set_code`, the recipe will fail at runtime with `ClassNotFoundException: CustomScalaRecipe` until the user opens it in the UI and saves it. There is no MCP path to trigger compilation.

## What to tell the user

Spark Scala recipes must be created and compiled through the DSS UI. After the user has created and saved the recipe in the UI (which triggers compilation), MCP tools can read settings with `get_recipe_settings` and run with `run_recipe`.

## DSS Reference

- Reference: `Spark-Scala recipes` (https://doc.dataiku.com/dss/latest/code_recipes/scala.html)
