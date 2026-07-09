"""Shared semantic-model command helpers."""

# ruff: noqa: F401

from __future__ import annotations

import uuid

import typer

from dku_cli.errors import exit_with_error, handle_api_error, is_already_exists_error
from dku_cli.helpers import (
    get_client_from_ctx,
    locked_settings,
    object_write_lock,
    read_json_input,
    resolve_project,
    resolve_semantic_model,
)
from dku_cli.output import (
    info,
    render,
    render_raw,
    resolve_output_format,
    success,
    warn,
)

app = typer.Typer(help="Manage DSS semantic models.")


def _default_attribute(column_name: str, dss_type: str, description: str = "") -> dict:
    """Build an attribute dict with DSS defaults from a dataset column."""
    attr = {
        "name": column_name,
        "dssType": dss_type,
        "type": "COLUMN",
        "column": column_name,
        "distinctValuesHandlingMode": "NONE",
        "manualValues": [],
        "indexDistinctValues": False,
        "resolveInUserRequests": False,
        "sqlGenerationConfig": {},
    }
    if description:
        attr["description"] = description
    return attr


def _column_description(col: dict) -> str:
    """Read a dataset schema column's description.

    DSS stores the schema-view "Description" field as `comment`
    (what `dku dataset ai-describe --save` and `set-column-description`
    write). `description` is accepted as a fallback for API payloads
    that use it.
    """
    return (col.get("comment") or col.get("description") or "").strip()


def _described_ratio(attrs: list[dict]) -> tuple[int, int]:
    """Return (described, total) counts over an entity's attributes."""
    return sum(1 for a in attrs if a.get("description")), len(attrs)


def _split_csv(value: str | None) -> list[str]:
    """Parse a comma-separated string into a trimmed list (empty string -> [])."""
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    """Remove duplicates while preserving first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _require_identifier(value: str, field_label: str) -> str:
    """Reject empty / whitespace-only identifiers. Returns stripped value."""
    stripped = (value or "").strip()
    if not stripped:
        exit_with_error(
            f"{field_label} cannot be empty or whitespace.",
            details=[
                f"Provide a non-blank {field_label.lower()}.",
            ],
        )
    return stripped


def _validate_columns_in_schema(
    columns: list[str],
    schema_cols: list[dict],
    flag_name: str,
    dataset: str,
) -> None:
    """Exit with error if any referenced column is missing from the dataset schema."""
    schema_names = {c.get("name") for c in schema_cols}
    missing = [c for c in columns if c not in schema_names]
    if missing:
        exit_with_error(
            f"{flag_name} references column(s) not in dataset '{dataset}': {', '.join(missing)}",
            details=[
                f"Available columns: {', '.join(sorted(schema_names)) if schema_names else '(none)'}",
                f"Check schema: dku dataset schema {dataset}",
                "Column names are case-sensitive.",
            ],
        )


def _load_version_settings(sm, version_id: str):
    """Return (settings_obj, raw_dict) for the given SM version.

    settings_obj.save() persists changes made to raw_dict in-place.
    """
    settings = sm.get_version(version_id).get_settings()
    return settings, settings.get_raw()


def _verify_entity_persisted(
    sm, version_id: str, entity_name: str, sm_ref: str, project_key: str
) -> None:
    """Re-read the version and exit loudly if the entity did not land.

    DSS accepts a write to a version whose settings doc isn't materialised and
    returns success without persisting anything — a silent no-op that leaves
    add-entity exiting 0 with nothing written. Read back so that failure is
    loud and prescriptive instead of a false success.

    A re-read that raises is a real DSS/API error (permissions, transport, a
    genuinely missing version), not evidence of a silent no-op — let it
    propagate to the caller's ``handle_api_error`` path rather than masking
    every failure as "did not persist". Only the case where the re-read
    succeeds and the entity is still absent warrants the persist error.
    """
    fresh = sm.get_version(version_id).get_settings().get_raw()
    names = {e.get("name") for e in fresh.get("entities", [])}
    if entity_name in names:
        return
    exit_with_error(
        f"Entity '{entity_name}' did not persist to version '{version_id}' — "
        "the write reported success but the entity is absent on re-read.",
        details=[
            f"Version '{version_id}' has no materialised settings doc to hold it.",
            f"Create it first: dku semantic-model create-version {sm_ref} {version_id} -P {project_key}",
            f"Then re-run the same add-entity with --version {version_id}.",
            f"Inspect versions: dku semantic-model versions {sm_ref} -P {project_key}",
        ],
    )


def _find_entity(raw: dict, entity_name: str) -> dict:
    """Find an entity dict by name, or exit with prescriptive error."""
    entities = raw.get("entities", [])
    for e in entities:
        if e.get("name") == entity_name:
            return e
    exit_with_error(
        f"Entity '{entity_name}' not found on version.",
        details=[
            "Available entities: "
            + (", ".join(e.get("name", "") for e in entities) or "(none)"),
        ],
    )


def _resolve_version_id(sm, version: str | None) -> str:
    """Resolve a version ID: explicit value or fall back to active version."""
    if version:
        return version
    try:
        return sm.get_active_version_id()
    except Exception:
        exit_with_error(
            "No active version set and --version not provided.",
            details=[
                f"List versions: dku semantic-model versions {sm.semantic_model_id} -P PROJECT",
                f"Set active: dku semantic-model set-active-version {sm.semantic_model_id} VERSION_ID -P PROJECT",
            ],
        )


def _load_command_version(
    ctx: typer.Context,
    project_key: str,
    sm_ref: str,
    version: str | None,
):
    """Resolve client/project/model/version and return mutable version settings."""
    client = get_client_from_ctx(ctx)
    proj = client.get_project(project_key)
    sm = resolve_semantic_model(proj, sm_ref)
    version_id = _resolve_version_id(sm, version)
    settings, raw = _load_version_settings(sm, version_id)
    return version_id, settings, raw


def _version_lock_key(sm, version_id: str) -> tuple[str, str]:
    """obj_type/obj_id pair identifying one semantic model version for locking.

    Different versions of the same model must not block each other, so the
    lock key includes both the model's own id and the version id.
    """
    return "semantic-model-version", f"{sm.semantic_model_id}/{version_id}"


def _version_settings_lock(
    client,
    project_key: str,
    sm,
    version_id: str,
    *,
    timeout_s: float = 60.0,
):
    """locked_settings(...) pre-filled with the semantic-model-version lock key.

    Saves unconditionally on a normal (non-exception) exit — use
    ``_version_write_lock`` instead when a mutation can legitimately decide
    not to save (e.g. an --if-not-exists skip).
    """
    obj_type, obj_id = _version_lock_key(sm, version_id)
    return locked_settings(
        client,
        project_key,
        obj_type,
        obj_id,
        sm.get_version(version_id).get_settings,
        timeout_s=timeout_s,
    )


def _version_write_lock(
    client,
    project_key: str,
    sm,
    version_id: str,
    *,
    timeout_s: float = 60.0,
):
    """object_write_lock(...) pre-filled with the semantic-model-version lock key.

    Bare lock — caller fetches, mutates, and calls settings.save() itself,
    for flows that may skip the save (e.g. an --if-not-exists no-op).
    """
    obj_type, obj_id = _version_lock_key(sm, version_id)
    return object_write_lock(client, project_key, obj_type, obj_id, timeout_s=timeout_s)


def _resolve_locked_version(
    ctx: typer.Context,
    project_key: str,
    sm_ref: str,
    version: str | None,
):
    """Resolve client/project/model/version — ingredients for a locked r-m-w."""
    client = get_client_from_ctx(ctx)
    proj = client.get_project(project_key)
    sm = resolve_semantic_model(proj, sm_ref)
    version_id = _resolve_version_id(sm, version)
    return client, proj, sm, version_id


def _locked_command_version(
    ctx: typer.Context,
    project_key: str,
    sm_ref: str,
    version: str | None,
):
    """Resolve client/project/model/version and return (version_id, lock).

    ``lock`` is a locked_settings context manager: entering it fetches fresh
    settings under the per-version write lock and saves on exit.
    """
    client, _proj, sm, version_id = _resolve_locked_version(
        ctx, project_key, sm_ref, version
    )
    return version_id, _version_settings_lock(client, project_key, sm, version_id)


def _append_named_item(
    items: list[dict],
    payload: dict,
    *,
    name_key: str,
    name: str,
    label: str,
    duplicate_scope: str,
    if_not_exists: bool,
    remove_hint: str,
) -> bool:
    """Append a named item or raise the repo-standard duplicate error."""
    if any(item.get(name_key) == name for item in items):
        if if_not_exists:
            warn(f"{label} '{name}' already exists{duplicate_scope}, skipping.")
            return False
        exit_with_error(
            f"{label} '{name}' already exists{duplicate_scope}.",
            details=[
                remove_hint,
                "Or pass --if-not-exists to skip.",
            ],
        )
    items.append(payload)
    return True


def _remove_named_item(
    container: dict,
    collection_key: str,
    *,
    name_key: str,
    name: str,
    label: str,
    missing_scope: str,
    list_hint: str,
) -> int:
    """Remove named items from a mutable collection or raise not_found."""
    items = container.get(collection_key, [])
    kept = [item for item in items if item.get(name_key) != name]
    removed = len(items) - len(kept)
    if removed == 0:
        exit_with_error(
            f"{label} '{name}' not found{missing_scope}.",
            details=[list_hint],
        )
    container[collection_key] = kept
    return removed


def _render_collection(
    items: list[dict],
    columns: list[str],
    *,
    output: str | None,
    title: str,
    row_builder,
) -> None:
    """Render a collection with a caller-owned row projection."""
    render(
        [row_builder(item) for item in items],
        columns,
        output_format=output,
        title=title,
    )


def _expression_payload(name: str, expression: str, description: str) -> dict:
    return {
        "name": name,
        "description": description,
        "pseudoSQLExpression": expression,
        "created": {},
    }


def _add_entity_expression_item(
    ctx: typer.Context,
    *,
    sm_ref: str,
    entity: str,
    name: str,
    expression: str,
    description: str,
    version: str | None,
    project_key: str,
    if_not_exists: bool,
    collection_key: str,
    label: str,
    remove_command: str,
) -> None:
    client, _proj, sm, version_id = _resolve_locked_version(
        ctx, project_key, sm_ref, version
    )
    with _version_write_lock(client, project_key, sm, version_id):
        settings, raw = _load_version_settings(sm, version_id)
        ent = _find_entity(raw, entity)
        items = ent.setdefault(collection_key, [])
        added = _append_named_item(
            items,
            _expression_payload(name, expression, description),
            name_key="name",
            name=name,
            label=label,
            duplicate_scope=f" on entity '{entity}'",
            if_not_exists=if_not_exists,
            remove_hint=(
                f"Remove first: dku semantic-model {remove_command} {sm_ref} "
                f"--entity {entity} --name '{name}' -P {project_key}"
            ),
        )
        if not added:
            return
        settings.save()
    success(
        f"Added {label.lower()} '{name}' to entity '{entity}' on version '{version_id}'"
    )


def _remove_entity_expression_item(
    ctx: typer.Context,
    *,
    sm_ref: str,
    entity: str,
    name: str,
    version: str | None,
    project_key: str,
    collection_key: str,
    label: str,
    list_command: str,
) -> None:
    _version_id, lock = _locked_command_version(ctx, project_key, sm_ref, version)
    with lock as settings:
        raw = settings.get_raw()
        ent = _find_entity(raw, entity)
        _remove_named_item(
            ent,
            collection_key,
            name_key="name",
            name=name,
            label=label,
            missing_scope=f" on entity '{entity}'",
            list_hint=(
                f"List {label.lower()}s: dku semantic-model {list_command} {sm_ref} "
                f"--entity {entity} -P {project_key}"
            ),
        )
    success(f"Removed {label.lower()} '{name}' from entity '{entity}'")


def _list_entity_expression_items(
    ctx: typer.Context,
    *,
    sm_ref: str,
    entity: str,
    version: str | None,
    project_key: str,
    output: str | None,
    collection_key: str,
    title_label: str,
) -> None:
    version_id, _, raw = _load_command_version(ctx, project_key, sm_ref, version)
    ent = _find_entity(raw, entity)
    _render_collection(
        ent.get(collection_key, []),
        ["name", "expression", "description"],
        output=output,
        title=f"{title_label} on '{entity}' (version {version_id})",
        row_builder=lambda item: {
            "name": item.get("name", ""),
            "expression": item.get("pseudoSQLExpression", ""),
            "description": item.get("description", ""),
        },
    )


__all__ = [name for name in globals() if not name.startswith("__")]
