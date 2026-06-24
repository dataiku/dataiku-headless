from __future__ import annotations

from dku_cli.output import warn


def update_dataset_metadata(
    ds,
    dataset_name: str,
    project_key: str,
    description: str | None,
    short_desc: str | None,
    tags: str | None,
) -> None:
    if description is not None or short_desc is not None:
        ds_def = ds.get_definition()
        if description is not None:
            ds_def["description"] = description
        if short_desc is not None:
            ds_def["shortDesc"] = short_desc
        ds.set_definition(ds_def)
        _warn_if_definition_not_persisted(
            ds, dataset_name, project_key, description, short_desc
        )

    if tags is not None:
        meta = ds.get_metadata()
        meta["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
        ds.set_metadata(meta)


def _warn_if_definition_not_persisted(
    ds,
    dataset_name: str,
    project_key: str,
    description: str | None,
    short_desc: str | None,
) -> None:
    after = ds.get_definition()
    reread = (
        f"Re-read with 'dku dataset get-definition {dataset_name} -P {project_key}'."
    )
    if short_desc is not None and after.get("shortDesc") != short_desc:
        warn(
            f"shortDesc did not persist (server returned "
            f"'{after.get('shortDesc', '')}'). {reread}"
        )
    if description is not None and after.get("description") != description:
        warn(
            f"description did not persist (server returned "
            f"'{after.get('description', '')}'). {reread}"
        )
