# Parameter Sets And Project Standards Checks

Start with [Plugin development](../plugin-development.md).

## Parameter Sets

Use `parameter-sets/<component-id>/parameter-set.json`, following the
[parameter-set tutorial](https://developer.dataiku.com/latest/tutorials/plugins/parameter-sets/generality/index.html).
A parameter set defines the fields; a preset holds their values. A component refers
to it through a `PRESET` parameter and `parameterSetId`. Choose where users can
configure presets, and use `CREDENTIAL_REQUEST` for supported per-user credentials.
Read the resolved values from the nested configuration, not from a preset's display name.

Test references and parsing with made-up values, then run a component with a preset
configured in the UI. Headless does not read or write installed preset values.
[API Connect](https://github.com/dataiku/dss-plugin-api-connect) has authentication examples.

## Project Standards Checks

Use `python-project-standards-check-specs/<component-id>/` with
`project_standards_check_spec.json` and `.py`, following the
[Project Standards tutorial](https://developer.dataiku.com/latest/tutorials/plugins/project-standards/flow-zone-check.html).
Distinguish a passing check, a quality failure, an inapplicable check, and an error
running the check. Explain the finding, affected objects, and how to fix it. A check
should inspect the project; repairs are a separate operation.

Test projects that pass, fail, and fall outside the check's scope. Register the
installed check and its scope in the Project Standards UI, then run it on a test project.
