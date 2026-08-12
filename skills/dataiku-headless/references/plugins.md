# Dataiku plugins

Use the plugin tools for instance-level plugin development and lifecycle operations. Plugin work is a documented direct-write exception because it is reusable, instance-level capability rather than a project asset.

Supported component directories include custom recipes, Python connectors, webapps, runnables/macros, agent tools and agents, guardrails, structured agent blocks, prepare steps, formats, filesystem providers, probes, checks, scenario steps and triggers, and parameter sets. Packaging remains generic, while validation checks the descriptor and implementation file required by each recognized component family.

## Recommended workflow

1. Inspect the installed plugin with `list_plugins`, `get_plugin`, and `get_plugin_usages`.
2. Scaffold or inspect the local source directory.
3. Edit local files with `write_local_plugin_file`, `move_local_plugin_file`, and `delete_local_plugin_file`.
4. Run `validate_plugin`, then `package_plugin`.
5. Install or update with `install_plugin`.
6. Create or assign the plugin-managed code environment, then rebuild it after dependency changes.
7. Re-read plugin metadata and usages to verify the result.

For a Python recipe, use `convert_python_recipe_to_plugin` after inspecting the source recipe with `get_recipe_settings`. The tool creates the native `custom-recipes/<id>/recipe.json` and `recipe.py` layout locally, preserves the source recipe unchanged, and returns review warnings for hard-coded dataset references or missing plugin parameters.

For a project WebApp, use `convert_webapp_to_plugin` after inspecting it with `get_webapp_settings`. It exports the WebApp descriptor and available source files into `webapps/<id>/` for review before packaging.

Plugin archives must contain `plugin.json` at their root. Local source paths are resolved and file operations cannot escape the plugin root. Installed-plugin file enumeration is available only for DSS development plugins.

Deletion checks usages by default. Use `force=true` only after reviewing the returned usage information and receiving the caller’s confirmation.

The tools use the active DSS instance and never accept or return API keys. They also support Plugin Store and Git installation/update when the DSS instance is configured for those sources.
