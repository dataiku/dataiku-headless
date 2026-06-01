# Cross-Project Sharing

## When You Need This

For a recipe or agent tool in project B to use an object from project A, project A must expose it to project B. This applies to datasets, managed folders, saved models, knowledge banks, and evaluation stores.

## CLI Support

`dku` does **not** currently expose cross-project object sharing. There is no `dku project share` / `list-shared` / `unshare` command. Configure cross-project exposure in the DSS UI (project A → *... > Share to another project*) or via the `dataikuapi` project settings.

Do not confuse this with flow-zone sharing below.

## Flow-Zone Sharing (intra-project)

`dku dataset share` / `unshare` operate on **flow zones within a single project** — they make a dataset visible in another zone of the same flow without moving it. This is not cross-project sharing.

```bash
dku dataset share my_data --zone Analytics -P PROJ
dku dataset unshare my_data --zone Analytics -P PROJ
```

## Safety Rules

- Flow-zone unsharing only affects in-project zone visibility; it does not break cross-project consumers.
- Cross-project exposure changes require `Read project conf` + `Write project conf` on the source project.
