"""dku flow — graph, zones, create-zone, set-zone, move, propagate, check, sources, successors."""

from __future__ import annotations

import contextlib
import io

import typer

from dku_cli.enums import MoveItemType
from dku_cli.errors import exit_with_error, handle_api_error, is_not_found_error
from dku_cli.helpers import (
    get_client_from_ctx,
    resolve_folder,
    resolve_knowledge_bank,
    resolve_project,
)
from dku_cli.output import (
    error,
    hint,
    info,
    render,
    render_dag,
    render_raw,
    resolve_output_format,
    success,
)

app = typer.Typer(help="Inspect and manage DSS project flow.")


@app.command()
def graph(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show flow graph summary."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        flow = proj.get_flow()
        graph_obj = flow.get_graph()

        if output == "json":
            render_raw(graph_obj.data, output_format="json")
        else:
            data = []
            for node_id, node in graph_obj.nodes.items():
                data.append(
                    {
                        "id": node_id,
                        "type": node.get("type", ""),
                        "subtype": node.get("subType", ""),
                        "ref": node.get("ref", node_id),
                    }
                )

            render(
                data,
                ["id", "type", "subtype", "ref"],
                output_format=output,
                title=f"Flow Graph ({project_key})",
            )
    except Exception as e:
        handle_api_error(e)


@app.command()
def visualize(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Render flow DAG as an ASCII tree."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        graph_obj = client.get_project(project_key).get_flow().get_graph()
        render_dag(graph_obj.nodes, f"Flow DAG ({project_key})")
    except Exception as e:
        handle_api_error(e)


@app.command()
def zones(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """List flow zones with their items (objectType + objectId per member).

    DSS reports the default zone's items[] as EMPTY even when it holds objects, so
    raw item counts mislead. This command derives the default zone's real
    membership (every flow node not assigned to another zone) and flags empty
    zones, so "is the flow clean?" can be judged from membership rather than a 0
    that lies. Derived members carry objectType=null and itemsDerived=true.
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        flow = proj.get_flow()
        zone_list = flow.list_zones()

        # Object ids explicitly assigned to a NON-default zone.
        zoned_ids: set[str] = set()
        for z in zone_list:
            if z.id == "default":
                continue
            for item in getattr(z, "_raw", {}).get("items", []) or []:
                oid = item.get("objectId")
                if oid:
                    zoned_ids.add(oid)

        # All flow nodes — used to derive the default zone's real membership.
        try:
            all_node_ids = set(flow.get_graph().nodes.keys())
        except Exception:
            all_node_ids = set()

        data = []
        for z in zone_list:
            raw_items = getattr(z, "_raw", {}).get("items", []) or []
            items = [
                {
                    "objectType": i.get("objectType"),
                    "objectId": i.get("objectId"),
                    "projectKey": i.get("projectKey", project_key),
                }
                for i in raw_items
            ]
            derived = False
            # The default zone's items[] is empty in the API; derive its members
            # as every flow node not claimed by another zone. The id stays
            # "default" even when the zone has been renamed.
            if z.id == "default" and not items and all_node_ids:
                members = sorted(all_node_ids - zoned_ids)
                items = [
                    {"objectType": None, "objectId": m, "projectKey": project_key}
                    for m in members
                ]
                derived = bool(members)
            data.append(
                {
                    "id": z.id,
                    "name": z.name,
                    "itemCount": len(items),
                    "itemsDerived": derived,
                    "items": items,
                }
            )

        # Default view only shows id/name/itemCount; items[] shipped via
        # --format json through render_raw to preserve the nested list.
        if output == "json":
            render_raw(data, output)
        else:
            render(
                data,
                ["id", "name", "itemCount"],
                output_format=output,
                title=f"Flow Zones ({project_key})",
            )
            empty = [d["name"] for d in data if d["itemCount"] == 0]
            if empty:
                info(
                    f"Empty zone(s): {', '.join(empty)} — no objects assigned. "
                    "(Default-zone members are derived; items[] is empty in the API.)"
                )
    except Exception as e:
        handle_api_error(e)


@app.command(
    "zone",
    hidden=True,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def _zone_noun_alias(ctx: typer.Context) -> None:
    """Hint for agents typing `dku flow zone <verb>` (kubectl-style noun-verb).

    Zone verbs live at the flow root, not under a `zone` sub-noun: `create-zone`,
    `set-zone`, `delete-zone`, and `zones` (list). Typer's "Did you mean" heuristic
    misses `create-zone` for the typo `zone create` because the leading token is
    different; this alias surfaces the right spelling instead of an empty error.
    """
    extra = ctx.args or []
    verb = extra[0] if extra else ""
    rewrites = {
        "create": "create-zone",
        "list": "zones",
        "delete": "delete-zone",
        "remove": "delete-zone",
        "rm": "delete-zone",
        "set": "set-zone",
        "update": "set-zone",
        "rename": "set-zone --name",
    }
    suggestion = rewrites.get(verb)
    error("`dku flow zone <verb>` is not a command — zone verbs live at the flow root.")
    if suggestion:
        rest = " ".join(extra[1:])
        info(f"Did you mean: `dku flow {suggestion}{(' ' + rest) if rest else ''}`?")
    else:
        info(
            "Available zone verbs: `dku flow create-zone NAME`, `dku flow zones` (list), "
            "`dku flow set-zone REF [--name X] [--color #...]`, `dku flow delete-zone REF [--force]`."
        )
    raise typer.Exit(2)


@app.command("create-zone")
def create_zone(
    ctx: typer.Context,
    name: str = typer.Argument(help="Zone name"),
    color: str | None = typer.Option(
        None, "--color", "-c", help="Zone color (hex, e.g. #FF5500)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create a new flow zone."""
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        flow = proj.get_flow()
        zone = flow.create_zone(name)
        if color is not None:
            settings = zone.get_settings()
            settings.color = color
            settings.save()
        success(f"Created zone '{name}' (id: {zone.id})")
        hint(f"dku flow graph -P {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command("set-zone")
def set_zone(
    ctx: typer.Context,
    zone_ref: str = typer.Argument(help="Zone name or ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    name: str | None = typer.Option(None, "--name", "-n", help="New zone name"),
    color: str | None = typer.Option(
        None, "--color", "-c", help="Zone color (hex, e.g. #FF5500)"
    ),
) -> None:
    """Update a flow zone's name and/or color."""
    if name is None and color is None:
        error("Provide --name and/or --color to update.")
        raise typer.Exit(1)
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        flow = proj.get_flow()
        zone = _resolve_zone(flow, zone_ref, project_key)
        settings = zone.get_settings()
        if name is not None:
            settings.name = name
        if color is not None:
            settings.color = color
        settings.save()
        success(f"Updated zone '{zone_ref}'")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command("delete-zone")
def delete_zone(
    ctx: typer.Context,
    zone_ref: str = typer.Argument(help="Zone name or ID"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    force: bool = typer.Option(
        False,
        "--force",
        help="Delete even if the zone has items (they move to the default zone).",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip safety guard"),
) -> None:
    """Delete a flow zone.

    By default only an EMPTY zone is deleted — the common case after moving a
    single-recipe flow's output into the same zone as its recipe leaves a
    leftover empty zone. A non-empty zone needs --force (its items are moved to
    the default zone, not deleted). The 'default' zone cannot be deleted.
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        flow = proj.get_flow()
        zone = _resolve_zone(flow, zone_ref, project_key)

        if zone.id == "default":
            exit_with_error(
                "The 'default' zone cannot be deleted.",
            )

        item_count = len(zone._raw.get("items", []))
        if item_count and not force:
            exit_with_error(
                f"Zone '{zone_ref}' has {item_count} item(s) — not deleting.",
                details=[
                    "Pass --force to delete it anyway (items move to the default "
                    "zone; they are NOT deleted).",
                    f"Inspect its items: dku flow zones -P {project_key}",
                ],
            )

        if item_count:
            # Non-empty + --force: reorganizes the flow → route through the guard.
            from dku_cli.safety import Tier, guard

            guard(
                ctx,
                tier=Tier.DELETE,
                action="flow.delete-zone",
                subject=f"flow zone '{zone.name}' ({zone.id}) with {item_count} item(s) in {project_key}",
                yes=yes,
                prompt=(
                    f"Delete flow zone '{zone.name}' ({zone.id}) from {project_key}? "
                    f"Its {item_count} item(s) will move to the default zone (not deleted)."
                ),
            )

        zone.delete()
        success(f"Deleted flow zone '{zone.name}' ({zone.id}) from {project_key}")
        if item_count:
            info(f"{item_count} item(s) were moved to the default zone.")
    except typer.Exit:
        raise
    except typer.Abort:
        raise
    except Exception as e:
        handle_api_error(e)


def _resolve_zone(
    flow, zone_ref: str, project_key: str, *, create_if_missing: bool = False
):
    """Resolve a zone by name (case-insensitive) or ID.

    When ``create_if_missing`` is True and the zone is not found, create a new
    zone using ``zone_ref`` as the name (only if ``zone_ref`` is not an id-style
    value with no spaces but unmatched in the existing list — we still treat it
    as a name). Returns the zone object.
    """
    zones = flow.list_zones()
    # Try exact ID match first
    for z in zones:
        if z.id == zone_ref:
            return z
    # Try case-insensitive name match
    for z in zones:
        if z.name.lower() == zone_ref.lower():
            return z
    # Not found
    if create_if_missing:
        new_zone = flow.create_zone(zone_ref)
        info(f"Created zone '{zone_ref}' (id: {new_zone.id})")
        return new_zone
    zone_list = ", ".join(f"'{z.name}' (id: {z.id})" for z in zones)
    exit_with_error(
        f"Zone '{zone_ref}' not found in project '{project_key}'.",
        details=[
            f"Available zones: {zone_list}",
            f"List zones: dku flow zones -P {project_key}",
            f'Create zone: dku flow create-zone "<name>" -P {project_key}',
        ],
    )


_ITEM_RESOLVERS = {
    "DATASET": "get_dataset",
    "RECIPE": "get_recipe",
    "MANAGED_FOLDER": "get_managed_folder",
    "SAVED_MODEL": "get_saved_model",
    # Both convert via flow._to_smart_ref: KB → RETRIEVABLE_KNOWLEDGE,
    # MES → MODEL_EVALUATION_STORE (use get_model_evaluation_store for every
    # flavor — DSSEvaluationStore is not accepted by _to_smart_ref).
    "KNOWLEDGE_BANK": "get_knowledge_bank",
    "MODEL_EVALUATION_STORE": "get_model_evaluation_store",
}


def _resolve_evaluation_store(proj, ref: str):
    """Resolve an evaluation store by ID or name to a DSSModelEvaluationStore."""
    try:
        mes = proj.get_model_evaluation_store(ref)
        mes.get_settings()  # lazy handle — confirm existence
        return mes
    except Exception:
        pass
    # Quirk: the raw fetch returns {id, name, mesFlavor} in one call; the
    # public list returns handles whose names need N+1 settings reads.
    for item in proj._fetch_evaluation_stores(flavor=None):
        if item.get("name") == ref:
            return proj.get_model_evaluation_store(item.get("id"))
    raise ValueError(f"Evaluation store '{ref}' not found (checked ID and name)")


def _resolve_saved_model(proj, ref: str):
    """Resolve a saved model by ID first, then by name.

    `proj.get_saved_model(sm_id)` only accepts the saved-model ID — passing
    a human-readable name silently returns a lazy handle whose
    `.get_settings()` raises NotFoundException. This falls back to a name
    match against `list_saved_models()` so `dku flow move <NAME>
    --type SAVED_MODEL` works the same way as `--type DATASET`.
    """
    sm = proj.get_saved_model(ref)
    try:
        sm.get_settings()
        return sm
    except Exception:
        pass
    # Fall back to name match.
    for entry in proj.list_saved_models() or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("name") == ref or entry.get("id") == ref:
            sm_id = entry.get("id")
            if sm_id:
                return proj.get_saved_model(sm_id)
    # No match — let the original NotFoundException surface.
    return sm


def _try_resolve_item(proj, name: str, item_type: str):
    """Resolve a single item by name+type, returning (obj, None) on success
    or (None, exception) on lookup failure."""
    try:
        if item_type == "MANAGED_FOLDER":
            return resolve_folder(proj, name), None
        if item_type == "KNOWLEDGE_BANK":
            return resolve_knowledge_bank(proj, name), None
        if item_type == "MODEL_EVALUATION_STORE":
            return _resolve_evaluation_store(proj, name), None
        if item_type == "SAVED_MODEL":
            obj = _resolve_saved_model(proj, name)
            obj.get_settings()
            return obj, None
        method = _ITEM_RESOLVERS[item_type]
        obj = getattr(proj, method)(name)
        # For datasets and recipes, lazy handles need a confirming call.
        if item_type == "DATASET":
            obj.get_definition()
        elif item_type == "RECIPE":
            obj.get_settings()
        return obj, None
    except SystemExit as exc:
        # resolve_folder / resolve_knowledge_bank call exit_with_error (sys.exit)
        # when nothing matches. During --type AUTO probing that must be a miss for
        # this kind, not a hard abort of the whole move — so catch SystemExit too.
        return None, exc
    except Exception as exc:
        return None, exc


def _detect_item_type(proj, name: str) -> str | None:
    """Try every known item type; return the first that resolves, or None.

    Used by `flow move --type AUTO` so agents can drop a mixed dataset +
    recipe + folder list into one call without pre-classifying each name.
    """
    # Probe non-exiting kinds first; MANAGED_FOLDER/KNOWLEDGE_BANK/MES resolvers
    # call exit_with_error (which prints + sys.exit) on a miss, so a saved model
    # or KB resolves before those run. Suppress the probe's stderr regardless so a
    # successful detection never leaks a spurious "not found" line.
    for kind in (
        "DATASET",
        "RECIPE",
        "SAVED_MODEL",
        "MANAGED_FOLDER",
        "KNOWLEDGE_BANK",
        "MODEL_EVALUATION_STORE",
    ):
        with contextlib.redirect_stderr(io.StringIO()):
            obj, exc = _try_resolve_item(proj, name, kind)
        if obj is not None and exc is None:
            return kind
    return None


@app.command()
def move(
    ctx: typer.Context,
    items: list[str] = typer.Argument(
        help="Item names to move. Use --type AUTO for mixed lists; otherwise --type sets the type for all items."
    ),
    zone: str = typer.Option(
        ...,
        "--zone",
        "-z",
        help="Target zone name or ID. Use 'dku flow zones' to list.",
    ),
    item_type: MoveItemType = typer.Option(
        MoveItemType.DATASET,
        "--type",
        "-t",
        case_sensitive=False,
        help=(
            "Item type for ALL items: DATASET (default), RECIPE, "
            "MANAGED_FOLDER, SAVED_MODEL, KNOWLEDGE_BANK, "
            "MODEL_EVALUATION_STORE, or AUTO to auto-detect each item."
        ),
    ),
    create_zone: bool = typer.Option(
        True,
        "--create-zone/--no-create-zone",
        help="Auto-create the zone if it doesn't exist (default: true). Use --no-create-zone to fail when the zone is missing.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Move items to a flow zone. Use instead of manually organizing in the DSS UI.

    Move datasets, recipes, folders, or models to a named zone. Pass
    ``--type AUTO`` to mix all four item types in a single call —
    each name is resolved against every kind and the first match wins.
    By default, creates the target zone if it does not yet exist —
    pass --no-create-zone to fail instead.

    When the explicit --type misses, the error suggests the right type
    instead of a dead-end "not found".

    Examples:
      dku flow move my_dataset --zone Processing -P PROJ
      dku flow move ds1 ds2 ds3 --zone Analytics -P PROJ
      dku flow move my_recipe --zone ETL --type RECIPE -P PROJ
      dku flow move ds_a recipe_b folder_c --type AUTO --zone Mixed -P PROJ
      dku flow move ds1 --zone Existing --no-create-zone -P PROJ
    """
    project_key = resolve_project(project)
    item_type_upper = item_type.upper()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        flow = proj.get_flow()

        target_zone = _resolve_zone(
            flow, zone, project_key, create_if_missing=create_zone
        )

        # Resolve item objects
        resolved = []
        for name in items:
            if item_type_upper == "AUTO":
                detected = _detect_item_type(proj, name)
                if detected is None:
                    exit_with_error(
                        f"'{name}' is not a dataset, recipe, managed folder, "
                        f"saved model, knowledge bank, or evaluation store "
                        f"in '{project_key}'.",
                        details=[
                            "Verify the name exists:",
                            f"  dku dataset list -P {project_key}",
                            f"  dku recipe list -P {project_key}",
                            f"  dku folder list -P {project_key}",
                            f"  dku model list -P {project_key}",
                            f"  dku knowledge list -P {project_key}",
                            f"  dku evaluation-store list -P {project_key}",
                        ],
                    )
                obj, _ = _try_resolve_item(proj, name, detected)
                resolved.append(obj)
                continue

            # Suppress the resolver's own pre-printed "not found" line so the
            # prescriptive cross-type guidance below is the single message the
            # agent sees (the exit_with_error-based folder/KB resolvers print to
            # stderr before raising SystemExit).
            with contextlib.redirect_stderr(io.StringIO()):
                obj, exc = _try_resolve_item(proj, name, item_type_upper)
            if obj is not None:
                resolved.append(obj)
                continue

            # SystemExit comes only from the exit_with_error-based resolvers
            # (MANAGED_FOLDER / KNOWLEDGE_BANK), which sys.exit solely on a
            # not-found miss — treat it as a miss so the cross-type probe runs
            # instead of re-raising a generic abort.
            if not exc or not (isinstance(exc, SystemExit) or is_not_found_error(exc)):
                raise exc

            # Cross-type miss: probe other kinds and tell the agent which
            # --type would have worked. Closes the recurring footgun where
            # `flow move ds_a recipe_b -z X` died with a useless error.
            other = _detect_item_type(proj, name)
            list_cmd = {
                "DATASET": "dataset list",
                "RECIPE": "recipe list",
                "MANAGED_FOLDER": "folder list",
                "SAVED_MODEL": "model list",
            }.get(item_type_upper, "dataset list")
            details = [
                f"List available: dku {list_cmd} -P {project_key}",
            ]
            if other:
                details.insert(
                    0,
                    f"'{name}' is a {other} — re-run with --type {other} "
                    f"or --type AUTO for mixed lists.",
                )
            exit_with_error(
                f"{item_type_upper} '{name}' not found in project '{project_key}'.",
                details=details,
            )

        # Move: batch for multiple, single for one
        if len(resolved) == 1:
            target_zone.add_item(resolved[0])
        else:
            target_zone.add_items(resolved)

        names = ", ".join(f"'{n}'" for n in items)
        success(f"Moved {names} to zone '{target_zone.name}' in {project_key}")
    except typer.Exit:
        raise
    except Exception as e:
        handle_api_error(e)


@app.command()
def propagate(
    ctx: typer.Context,
    dataset: str = typer.Argument(help="Starting dataset name for schema propagation"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
    stop_at: list[str] | None = typer.Option(
        None, "--stop-at", help="Recipe to stop propagation at (repeatable)"
    ),
    mark_ok: list[str] | None = typer.Option(
        None, "--mark-ok", help="Recipe to mark as OK during propagation (repeatable)"
    ),
    no_auto_rebuild: bool = typer.Option(
        False, "--no-auto-rebuild", help="Disable automatic rebuild during propagation"
    ),
) -> None:
    """Run schema propagation from a dataset through downstream recipes."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        flow = proj.get_flow()

        builder = flow.new_schema_propagation(dataset)
        if no_auto_rebuild:
            builder.set_auto_rebuild(False)
        for recipe_name in stop_at or []:
            builder.stop_at(recipe_name)
        for recipe_name in mark_ok or []:
            builder.mark_recipe_as_ok(recipe_name)

        result = builder.start().wait_for_result()

        render_raw(result, output_format=output)
        success(f"Schema propagation from '{dataset}' complete.")
    except Exception as e:
        handle_api_error(e)


@app.command()
def check(
    ctx: typer.Context,
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Run flow consistency check (schema + data consistency)."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        flow = proj.get_flow()

        tool = flow.start_tool("CHECK_CONSISTENCY")
        try:
            future = tool.update(
                {
                    "recheckAll": True,
                    "datasets": {"consistencyWithData": True},
                    "recipes": {
                        "schemaConsistency": True,
                        "otherExpensiveChecks": False,
                    },
                }
            )
            future.wait_for_result()
            state = tool.get_state()
            summary = state.get("summary", {})
            errors = []
            for node_id, node_state in state.get("stateByNode", {}).items():
                for check_key in ("recipeCheckResult", "datasetCheckResult"):
                    check = node_state.get(check_key, {})
                    for msg in check.get("messages", []):
                        if msg.get("isFatal") or msg.get("severity") in (
                            "ERROR",
                            "FATAL",
                        ):
                            errors.append(
                                {
                                    "node": node_id,
                                    "code": msg.get("code", ""),
                                    "message": msg.get("message", ""),
                                }
                            )
            if output == "json":
                render_raw({"summary": summary, "errors": errors}, output_format="json")
            else:
                render(
                    [{"field": k, "value": str(v)} for k, v in summary.items()],
                    ["field", "value"],
                    output_format=output,
                    title=f"Flow Check Summary ({project_key})",
                )
                if errors:
                    render(
                        errors,
                        ["node", "code", "message"],
                        output_format=output,
                        title="Errors",
                    )
                success("Consistency check complete.")
        finally:
            try:
                tool.stop()
            except Exception:
                pass
    except Exception as e:
        handle_api_error(e)


@app.command()
def sources(
    ctx: typer.Context,
    dataset: str = typer.Argument(
        None, help="Dataset to find upstream sources for (omit for all project sources)"
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Find source datasets (nodes with no upstream dependencies).

    Without an argument, lists all root sources in the project.
    With a dataset argument, traces upstream from that dataset to find its sources.
    """
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        flow = proj.get_flow()
        graph_obj = flow.get_graph()

        if dataset:
            # Trace upstream from the given dataset to find its sources
            # Build reverse adjacency: child -> set of parents
            parents: dict[str, set[str]] = {}
            for node_id, node in graph_obj.nodes.items():
                for succ in node.get("successors", []):
                    parents.setdefault(succ, set()).add(node_id)

            # BFS upstream from target
            visited: set[str] = set()
            queue = [dataset]
            source_nodes: list[str] = []
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                ups = parents.get(current, set())
                if not ups:
                    source_nodes.append(current)
                else:
                    queue.extend(ups)

            data = []
            for node_id in source_nodes:
                node = graph_obj.nodes.get(node_id, {})
                data.append(
                    {
                        "id": node_id,
                        "type": node.get("type", ""),
                        "ref": node.get("ref", node_id),
                    }
                )

            title = f"Sources of {dataset} ({project_key})"
        else:
            # Original behavior: all project root sources
            downstream_nodes: set[str] = set()
            for node_id, node in graph_obj.nodes.items():
                successors = node.get("successors", [])
                downstream_nodes.update(successors)

            data = []
            for node_id, node in graph_obj.nodes.items():
                if node_id not in downstream_nodes:
                    data.append(
                        {
                            "id": node_id,
                            "type": node.get("type", ""),
                            "ref": node.get("ref", node_id),
                        }
                    )

            title = f"Source Nodes ({project_key})"

        render(
            data,
            ["id", "type", "ref"],
            output_format=output,
            title=title,
        )
    except Exception as e:
        handle_api_error(e)


@app.command()
def successors(
    ctx: typer.Context,
    node: str = typer.Argument(help="Node ID to find successors for"),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Show downstream successors of a flow node."""
    project_key = resolve_project(project)
    output = resolve_output_format()
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        flow = proj.get_flow()
        graph_obj = flow.get_graph()

        # Try graph_obj.get_successors() first, fall back to parsing nodes
        try:
            successor_ids = graph_obj.get_successors(node)
        except (AttributeError, TypeError):
            # Parse from graph data — look for "successors" list on the node
            node_data = graph_obj.nodes.get(node, {})
            successor_ids = node_data.get("successors", [])

        data = []
        for s_id in successor_ids:
            s_node = graph_obj.nodes.get(s_id, {})
            data.append(
                {
                    "id": s_id,
                    "type": s_node.get("type", ""),
                    "ref": s_node.get("ref", s_id),
                }
            )

        render(
            data,
            ["id", "type", "ref"],
            output_format=output,
            title=f"Successors of {node} ({project_key})",
        )
    except Exception as e:
        handle_api_error(e)
