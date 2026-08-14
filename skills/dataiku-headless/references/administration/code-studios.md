---
name: code-studios
description: Inspect and administer Dataiku Code Studio templates and project Code Studios.
---

# Code Studios

Use this guide for Code Studio template administration or project Studio lifecycle work.

## Workflow

1. Inspect templates with `list_code_studio_templates` and `get_code_studio_template_settings`.
2. Patch only the required settings with `update_code_studio_template`, then use `build_code_studio_template`.
3. Create project Studios with `create_code_studio`, then use `start_code_studio` and `get_code_studio` to verify readiness.

## Safety

- Template tools require Dataiku administrator access.
- Template settings may contain credentials; reads redact credential-shaped values. Do not copy redacted values back into a patch.
- A template build is asynchronous; retain its `future_id` and inspect it with `get_future_status`.
- This increment does not expose Studio terminal/file synchronization or deletion.
