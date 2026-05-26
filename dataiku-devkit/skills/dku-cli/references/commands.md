# dku-cli Command Reference

Use this entrypoint to choose the right command syntax reference. Detailed command sections were split so agents can load only the relevant surface.

Global options available on the root CLI:

```bash
dku [--url URL] [--api-key KEY] [--profile NAME] [--quiet] [--errors text|json] [--dangerous] COMMAND ...
```

## Ownership

- Safety and exit-77 recovery: `safety.md`
- Build/chaining/verification workflows: `recipe-operations.md`
- Operational traps and recovery snippets: `common-gotchas.md`
- Recipe selection rationale: `recipe-decision.md` and `recipe-survey.md`

## Split References

| Need | Read |
|---|---|
| Auth, config, project, dataset, recipe, scenario, job, folder, flow, library, SQL, whoami | `commands-core.md` |
| LLM, ML, models, Knowledge Banks, agents, semantic models, dashboards, insights, webapps, app designer, notebooks, wiki | `commands-ai-apps.md` |
| Plugins, code envs, connections, users, deployers, Git, bundles, API services, admin, clusters, API keys, workspaces | `commands-admin-deploy.md` |
| Govern commands | `commands-govern.md` |
| Compact verb matrix | `commands-list.md` |

## Global Notes

- Root options must appear before the command group: `dku --errors json recipe list`, not `dku recipe list --errors json`.
- Use `-o json` for scripting; JSON goes to stdout and status messages go to stderr.
- Project-scoped commands accept `-P PROJECT` unless otherwise documented.
- Destructive commands may require `--yes` or `--confirm-name`; read `safety.md` before retrying a blocked command.
