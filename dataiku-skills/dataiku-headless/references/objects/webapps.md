# WebApps

A WebApp combines an interface, framework-specific code, an optional backend, and
project-object integrations. Read its persisted settings with
`get_object_settings(object_type="webapp")`; live backend state is a separate
runtime fact this surface does not read.

| Type | Framework |
|---|---|
| `STANDARD` | HTML, CSS, JavaScript, and optional Python backend |
| `DASH` | Python Dash |
| `BOKEH` | Python Bokeh |
| `SHINY` | R UI and server |
| `STREAMLIT` | Python Streamlit |

Discover the type from settings rather than the name. Inspect referenced
datasets, folders, models, APIs, code environments, and library files when they
affect a change. A backend restart or stop interrupts users; delegate that action
to Cobuild only when the user needs it.
