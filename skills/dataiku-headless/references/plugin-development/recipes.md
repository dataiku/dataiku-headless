# Recipe Plugin Components

Start with [Plugin development](../plugin-development.md). Use
`custom-recipes/<component-id>/recipe.json` and the language entry point, following
[the recipe reference](https://doc.dataiku.com/dss/latest/plugins/reference/recipes.html).

## Roles And Schemas

- Make `kind`, accepted object types, role `arity`, and `required` match the code.
  Get inputs and outputs with `get_input_names_for_role` and
  `get_output_names_for_role`, handling optional or multiple objects as declared.
- A recipe `COLUMN` parameter references an input role through `columnRole`.
- Define the output schema and validate configured columns. Process data in chunks
  or streams when loading the full input would use too much memory.

## Cobuild Integration

Plugin recipe support starts with Dataiku **14.7.4 and 15.0.1**. Opt in with this
top-level `recipe.json` property:

```json
"cobuild": {"supported": true}
```

Cobuild infers configuration from the descriptor, not the code. Declare role and
parameter constraints accurately, including conditional visibility: a parameter is
required when mandatory and visible. Prefer presets for authentication.

Add `custom-recipes/<component-id>/Cobuild.md` to explain parameter relationships,
units, or output behavior that the descriptor cannot express. Cobuild cannot retrieve
dynamic choices from `getChoicesFromPython`; use values supplied by the user or
explained in the component guidance, or ask the user to select them in the UI.
Reload after descriptor changes. See [integration details](https://doc.dataiku.com/dss/latest/plugins/reference/recipes.html#make-a-plugin-recipe-available-to-cobuild).

## Verification And Example

Test transformation values and schemas. In Dataiku, confirm Cobuild can configure the
intended roles and parameters. Execute the recipe and inspect its dataset or folder outputs.
[NLP Preparation](https://github.com/dataiku/dss-plugin-nlp-preparation) illustrates
short entry points, shared processing code, chunked processing, and separate unit
and integration tests.
