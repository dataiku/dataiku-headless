# WebApps

A WebApp combines an interface, framework-specific code, an optional backend, and
project-object integrations. Persisted settings and live backend state are
separate evidence.

| Type | Framework |
|---|---|
| `STANDARD` | HTML, CSS, JavaScript, and optional Python backend |
| `DASH` | Python Dash |
| `BOKEH` | Python Bokeh |
| `SHINY` | R UI and server |
| `STREAMLIT` | Python Streamlit |

Discover the type from settings rather than the name. Inspect referenced
datasets, folders, models, APIs, code environments, and library files when they
affect a change. A backend restart or stop interrupts users; request it only when
the user needs that action, then re-check `get_webapp_state`.
