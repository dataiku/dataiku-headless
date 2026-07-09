"""Flow utilities for managing recipes and datasets."""

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.serialization import columnar, compact_json, omit_empty
from .utils.auth import get_dss_client
from .utils.parsing import coerce_json_object as _coerce_json_object
from .utils.validation import (
    require_allowed_value as _require_allowed_value,
    require_hex_color as _require_hex_color,
    require_non_empty_string as _require_non_empty_string,
)

# Object types whose settings extend DSSTaggableObjectSettings.
_TAGGABLE_TYPES = {
    "dataset",
    "recipe",
    "managed_folder",
    "agent",
    "retrieval_augmented_llm",
    "knowledge_bank",
}

# Saved models use raw dict access (DSSSavedModelSettings does not extend
# DSSTaggableObjectSettings but stores the same top-level metadata fields).
_METADATA_OBJECT_TYPES = _TAGGABLE_TYPES | {"saved_model"}


def _get_metadata_settings(project, object_type: str, object_name: str):
    if object_type == "dataset":
        return project.get_dataset(object_name).get_settings()
    if object_type == "recipe":
        return project.get_recipe(object_name).get_settings()
    if object_type == "managed_folder":
        return project.get_managed_folder(object_name).get_settings()
    if object_type == "saved_model":
        return project.get_saved_model(object_name).get_settings()
    if object_type == "agent":
        return project.get_agent(object_name).get_settings()
    if object_type == "retrieval_augmented_llm":
        return project.get_retrieval_augmented_llm(object_name).get_settings()
    if object_type == "knowledge_bank":
        return project.get_knowledge_bank(object_name).get_settings()


def _read_metadata(settings, object_type: str) -> dict:
    if object_type in _TAGGABLE_TYPES:
        meta = {
            "short_description": settings.short_description,
            "description": settings.description,
            "tags": settings.tags,
            "custom_fields": settings.custom_fields,
        }
    else:
        raw = settings.get_raw()
        meta = {
            "short_description": raw.get("shortDesc"),
            "description": raw.get("description"),
            "tags": raw.get("tags", []),
            "custom_fields": raw.get("customFields"),
        }
    # Lever 4: omit empty metadata fields (absent reads as empty by JSON convention).
    # Keeps False / 0 since those are not equal to None/""/[]/{}.
    return omit_empty(meta)


def _write_metadata(settings, updates: dict, object_type: str) -> None:
    if object_type in _TAGGABLE_TYPES:
        if "short_description" in updates:
            settings.short_description = updates["short_description"]
        if "description" in updates:
            settings.description = updates["description"]
        if "tags" in updates:
            settings.tags = updates["tags"]
        if "custom_fields" in updates:
            settings.custom_fields = updates["custom_fields"]
    else:
        raw = settings.get_raw()
        if "short_description" in updates:
            raw["shortDesc"] = updates["short_description"]
        if "description" in updates:
            raw["description"] = updates["description"]
        if "tags" in updates:
            raw["tags"] = updates["tags"]
        if "custom_fields" in updates:
            raw["customFields"] = updates["custom_fields"]
    settings.save()


def _short_type(node_type):
    """Drop the redundant COMPUTABLE_/RUNNABLE_ prefix and lowercase (lossless)."""
    if not node_type:
        return node_type
    for prefix in ("COMPUTABLE_", "RUNNABLE_"):
        if node_type.startswith(prefix):
            return node_type[len(prefix):].lower()
    return node_type.lower()


def _simplify_flow_node(node: dict) -> list:
    # [ref, type] pair; traversal order is carried by list position
    return [node.get("ref"), _short_type(node.get("type"))]


@mcp.tool()
async def get_flow_items_in_traversal_order(
    project_key: str,
    ctx: Context,
) -> str:
    """List the flow items in left-to-right traversal order; each item is a [ref, type] pair."""
    project_key = _require_non_empty_string(project_key, "project_key")

    await ctx.info(f"Loading flow traversal order for {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        flow = project.get_flow()
        graph = flow.get_graph()
        return graph.get_items_in_traversal_order(as_type="dict")

    traversal_order_all = await run_blocking(_run)
    return compact_json(
        {
            "project_key": project_key,
            "item_count": len(traversal_order_all),
            "items": [_simplify_flow_node(node) for node in traversal_order_all],
        }
    )


@mcp.tool()
async def list_flow_zones(project_key: str, ctx: Context) -> str:
    """List the flow zones in the project with their items."""
    project_key = _require_non_empty_string(project_key, "project_key")

    await ctx.info(f"Listing flow zones in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        flow = project.get_flow()
        return [zone.get_settings().get_raw() for zone in flow.list_zones()]

    zones_raw = await run_blocking(_run)
    return compact_json(
        {
            "zones": columnar(
                [
                    {
                        "zone_id": zone_raw.get("id"),
                        "name": zone_raw.get("name"),
                        "description": zone_raw.get("description"),
                        "items": [
                            {"object_type": i.get("objectType"), "object_id": i.get("objectId")}
                            for i in zone_raw.get("items", [])
                        ],
                    }
                    for zone_raw in zones_raw
                ],
                ["zone_id", "name", "description", "items"],
            ),
        }
    )


@mcp.tool()
async def create_flow_zone(
    project_key: str,
    zone_name: str,
    ctx: Context,
    color: str = "#2ab1ac",
) -> str:
    """Create a new flow zone.

    Args:
        color: Hex color in #RRGGBB format
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    zone_name = _require_non_empty_string(zone_name, "zone_name")
    color = _require_hex_color(color, "color")

    await ctx.info(f"Creating flow zone '{zone_name}' in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        flow = project.get_flow()
        zone = flow.create_zone(zone_name, color=color)
        return zone.get_settings().get_raw()

    zone_raw = await run_blocking(_run)
    return compact_json(
        {
            "zone_name": zone_raw.get("name"),
            "zone_id": zone_raw.get("id"),
            "color": zone_raw.get("color"),
        }
    )


@mcp.tool()
async def delete_flow_zone(
    project_key: str,
    zone_id: str,
    ctx: Context,
) -> str:
    """Delete a flow zone. Items in the zone are moved to the default zone."""
    if zone_id == "default":
        raise ValueError("Cannot delete the 'default' flow zone.")

    project_key = _require_non_empty_string(project_key, "project_key")
    zone_id = _require_non_empty_string(zone_id, "zone_id")

    await ctx.info(f"Deleting flow zone '{zone_id}' in {project_key}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        flow = project.get_flow()
        zone = flow.get_zone(zone_id)
        return zone.delete()

    await run_blocking(_run)

    return compact_json({})


@mcp.tool()
async def add_items_to_flow_zone(
    project_key: str,
    zone_id: str,
    items: list[dict],
    ctx: Context,
) -> str:
    """Add items to a flow zone (automatically moved from their current zones).

    Args:
        items: Each item is {object_type, object_id}. object_type is one of DATASET, RECIPE, MANAGED_FOLDER, SAVED_MODEL, RETRIEVABLE_KNOWLEDGE, MODEL_EVALUATION_STORE.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    zone_id = _require_non_empty_string(zone_id, "zone_id")

    await ctx.info(f"Adding {len(items)} item(s) to flow zone '{zone_id}' in {project_key}...")

    def _resolve(project, object_type: str, object_id: str):
        t = object_type.upper()
        if t == "DATASET":
            return project.get_dataset(object_id)
        if t == "MANAGED_FOLDER":
            return project.get_managed_folder(object_id)
        if t == "SAVED_MODEL":
            return project.get_saved_model(object_id)
        if t == "RECIPE":
            return project.get_recipe(object_id)
        if t == "RETRIEVABLE_KNOWLEDGE":
            return project.get_knowledge_bank(object_id)
        if t == "MODEL_EVALUATION_STORE":
            return project.get_model_evaluation_store(object_id)
        raise ValueError(
            f"Unsupported object_type '{object_type}'. Use DATASET, RECIPE, "
            "MANAGED_FOLDER, SAVED_MODEL, RETRIEVABLE_KNOWLEDGE, or MODEL_EVALUATION_STORE."
        )

    def _run():
        project = get_dss_client().get_project(project_key)
        flow = project.get_flow()
        zone = flow.get_zone(zone_id)
        resolved = [_resolve(project, i["object_type"], i["object_id"]) for i in items]
        zone.add_items(resolved)
        return {"items_added": len(resolved)}

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def propagate_schema(project_key: str, dataset_name: str, ctx: Context) -> str:
    """Propagate schema changes from a dataset downstream through the flow. Useful after editing an upstream recipe or input dataset."""
    project_key = _require_non_empty_string(project_key, "project_key")
    dataset_name = _require_non_empty_string(dataset_name, "dataset_name")

    await ctx.info(f"Propagating schema from {dataset_name}...")

    def _run():
        project = get_dss_client().get_project(project_key)
        flow = project.get_flow()
        propagation = flow.new_schema_propagation(dataset_name)
        return propagation.start().wait_for_result()

    result = await run_blocking(_run)
    out = {
        "propagation_success": not (result["error"] or result["fatal"]),
        "propagation_messages": result["messages"],
    }
    # Lever 4: omit propagation_messages when there are none ([] reads as absent).
    if out["propagation_messages"] in (None, [], {}):
        del out["propagation_messages"]
    return compact_json(out)


@mcp.tool()
async def get_flow_object_metadata(
    project_key: str,
    object_type: str,
    object_name: str,
    ctx: Context,
) -> str:
    """Get the metadata (short/long description, tags, custom fields) for a flow object.

    Args:
        object_type: One of "dataset", "recipe", "managed_folder", "saved_model",
            "agent", "retrieval_augmented_llm", "knowledge_bank"
        object_name: Dataset or recipe name; object ID for all other types
    """
    _require_allowed_value(object_type, "object_type", _METADATA_OBJECT_TYPES)
    await ctx.info(
        f"Fetching metadata for {object_type} '{object_name}' in {project_key}..."
    )

    def _run():
        project = get_dss_client().get_project(project_key)
        settings = _get_metadata_settings(project, object_type, object_name)
        return _read_metadata(settings, object_type)

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def set_flow_object_metadata(
    project_key: str,
    object_type: str,
    object_name: str,
    metadata,
    ctx: Context,
) -> str:
    """Set metadata fields on a flow object. Only the fields present in the metadata
    object are updated; omitted fields are left unchanged.

    Call get_flow_object_metadata first to inspect the current state.

    Note: "agent" and "retrieval_augmented_llm" do not support metadata writes
    (Dataiku bug — the backend silently ignores them).

    Args:
        object_type: One of "dataset", "recipe", "managed_folder", "saved_model",
            "agent", "retrieval_augmented_llm", "knowledge_bank"
        object_name: Dataset or recipe name; object ID for all other types
        metadata: Object with any subset of: short_description, description, tags,
            custom_fields
    """
    _require_allowed_value(object_type, "object_type", _METADATA_OBJECT_TYPES)
    metadata_obj = _coerce_json_object(metadata, "metadata")
    await ctx.info(
        f"Updating metadata for {object_type} '{object_name}' in {project_key}..."
    )

    def _run():
        project = get_dss_client().get_project(project_key)
        settings = _get_metadata_settings(project, object_type, object_name)
        _write_metadata(settings, metadata_obj, object_type)

    await run_blocking(_run)
    return compact_json(
        {
            "updated_fields": list(metadata_obj.keys()),
        }
    )
