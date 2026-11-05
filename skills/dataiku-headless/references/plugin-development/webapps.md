# Webapp Plugin Components

Start with [Plugin development](../plugin-development.md). Users configure a separate
webapp in each project that uses the plugin component.

Follow the [component reference](https://doc.dataiku.com/dss/latest/plugins/reference/webapps.html)
and [conversion tutorial](https://developer.dataiku.com/latest/tutorials/plugins/webapps/generality/index.html).
Convert a working webapp in the UI to get starter code for its type. Check the
generated files: webapp types can use different backends and filenames.

- Standard components use `webapps/<component-id>/webapp.json` and type-specific files.
- `DATASET_COLUMN` references a dataset setting through `datasetParamName`; recipe
  `COLUMN` parameters instead use an input role's `columnRole`.
- Read settings through the type's API, such as `dataiku.getWebAppConfig()` in standard
  JavaScript or `get_webapp_config()` in Python. Keep credentials on the backend.
- Include the current built frontend assets. Check that resource URLs, backend
  routes, and settings work in Dataiku as well as on a local development server.
- Keep styles and JavaScript scoped to the app, and check access to backend routes.

In Dataiku, check rendering, configured datasets and columns, asset loading, backend
startup, and what users see when data is empty or a request fails.
[Flow Charts](https://github.com/dataiku/dss-plugin-flow-charts) has small frontend-only
examples; use current starters rather than adopting its older frontend dependencies.
