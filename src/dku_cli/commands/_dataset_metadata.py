from __future__ import annotations

from dku_cli.errors import exit_with_error, is_not_found_error
from dku_cli.helpers import get_client_from_ctx
from dku_cli.output import success, warn

# DSS computes these server-side; they're absent on create and reappear on the
# next GET, so a get-definition -> set-definition round-trip must not send
# them back (and unpersisted_key_paths would otherwise flag them as dropped).
NON_PERSISTED_DEFINITION_KEYS = {"smartName"}


def drop_non_persisted_keys(payload: dict) -> dict:
    """Remove DSS-computed keys (e.g. smartName) from a definition payload in place."""
    for key in NON_PERSISTED_DEFINITION_KEYS:
        payload.pop(key, None)
    return payload


def _warn_if_rename_left_stale_path(
    ds, dataset_name: str, new_name: str, project_key: str
) -> None:
    """Warn when a managed dataset's storage path still points at the old name.

    DSS's renameDataset action is metadata-only: params.path is not moved, so
    a dataset later created under the vacated old name gets the same default
    path and collides with this one on disk.
    """
    try:
        path = ds.get_definition().get("params", {}).get("path")
    except Exception:  # quality-ratchet: allow-broad-exception
        return
    if path and path.rsplit("/", 1)[-1] == dataset_name:
        warn(
            f"Storage path still '{path}' (unchanged by rename) — a new "
            f"dataset created later under '{dataset_name}' will get the "
            "same default path and collide on disk."
        )
        warn(f"Inspect with: dku dataset get-definition {new_name} -P {project_key}")


def rename_dataset(ctx, dataset_name: str, new_name: str, project_key: str) -> None:
    """Rename a dataset and warn if its storage path was left stale."""
    client = get_client_from_ctx(ctx)
    ds = client.get_project(project_key).get_dataset(dataset_name)
    ds.rename(new_name)
    success(f"Renamed '{dataset_name}' to '{new_name}'")
    _warn_if_rename_left_stale_path(ds, dataset_name, new_name, project_key)


def copy_dataset(
    ctx, dataset_name: str, to_project: str, new_name: str, project_key: str
) -> None:
    """Copy dataset data into an existing dataset in another project."""
    client = get_client_from_ctx(ctx)
    ds = client.get_project(project_key).get_dataset(dataset_name)
    target_ds = client.get_project(to_project).get_dataset(new_name)
    ds.copy_to(target_ds)
    success(f"Copied '{dataset_name}' to {to_project}.{new_name}")


def raise_if_copy_destination_missing(
    e: Exception, project_key: str, dataset_name: str, to_project: str, new_name: str
) -> None:
    """Exit with prescriptive guidance if `e` is a target-side not-found for
    `dataset copy`; otherwise return so the caller falls through to the
    generic handler.

    `dataset copy` requires the destination to already exist; DSS's generic
    not-found handler otherwise misdirects toward a typo. Falls through when
    the error instead names the SOURCE.
    """
    if not is_not_found_error(e):
        return
    # Match on qualified PROJECT.dataset names: bare-key substring checks
    # misfire when one project key prefixes the other (TEST vs TEST2 — DSS
    # says "dataset does not exist: TEST2.raw" and "TEST" is a substring).
    msg = str(e)
    source_named = f"{project_key}.{dataset_name}" in msg
    target_named = f"{to_project}.{new_name}" in msg
    if not (target_named and not source_named):
        return
    exit_with_error(
        f"Destination dataset {to_project}.{new_name} does not exist.",
        status=3,
        details=[
            "`dataset copy` copies data only — create the target first:",
            f"  dku dataset create {new_name} --type <TYPE> --connection "
            f"<CONN> -P {to_project}",
            f"  dku dataset set-schema {new_name} -P {to_project} -d '<schema>'",
            f"Then retry: dku dataset copy {dataset_name} --to-project "
            f"{to_project} --name {new_name} -P {project_key}",
        ],
    )


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
