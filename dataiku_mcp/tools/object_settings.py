"""One generic deep-read over the object types Cobuild builds.

PR 4 deleted the narrow per-type deep-read tools (``get_agent_settings``,
``get_dashboard_settings``, ``get_wiki_article``, …) and told the supervisor to
inspect those objects "via a read-only Cobuild turn". That left the builder
grading its own homework: the skill's own rule is *Cobuild's report is testimony,
not evidence — verify with your own reads*, yet for agents/dashboards/wikis/
semantic-models the only surviving read path was asking Cobuild.

This restores an INDEPENDENT read path without restoring 43 tools. One tool,
``get_object_settings``, dispatches on a closed ``object_type`` enum to the exact
``dataikuapi`` call the deleted tool used, returns the raw settings dict, redacts
secret-bearing keys with the shared heuristic, and bounds the payload to a hard
byte ceiling. Object types that already have their own deep reads (datasets,
recipes, scenarios, connections, folders, jobs, projects) are intentionally NOT
covered here — reach for their dedicated tools.
"""

from __future__ import annotations

from typing import Any, Callable

from dataikuapi.utils import DataikuException
from fastmcp import Context

from .. import mcp
from .machine_learning.shared.common import require_single_ml_task
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.redaction import VARIABLE_REDACTION, redact_sensitive_values
from .utils.serialization import compact_json
from .utils.validation import (
    require_allowed_value as _require_allowed_value,
    require_non_empty_string as _require_non_empty_string,
)

# Hard server ceiling on the serialized settings blob. Raw settings dicts (an ML
# task's per-feature config, a structured agent's block graph) can be large; the
# read is always bounded so a single object can never return an unbounded
# payload. When the compact-JSON settings exceed this, the blob is clipped on a
# UTF-8 boundary and the response carries ``truncated: true`` with byte counts —
# the same shape ``read_project_library_file`` uses for oversized files.
MAX_SETTINGS_BYTES = 1_000_000

# ``version_id`` addresses a specific version of a versioned object. It is
# REQUIRED for the two types whose deep read is a per-version detail, OPTIONAL
# for agents (defaults to the full multi-version settings), and rejected for
# every other type so a caller learns the argument is inert rather than silently
# ignored.
_VERSION_REQUIRED_TYPES = frozenset({"saved_model", "semantic_model"})
_VERSIONED_TYPES = _VERSION_REQUIRED_TYPES | {"agent"}


def _wiki_article(project, object_id: str, version_id: str) -> dict[str, Any]:
    data = project.get_wiki().get_article(object_id).get_data()
    return {"name": data.get_name(), "body": data.get_body()}


def _dashboard(project, object_id: str, version_id: str) -> dict[str, Any]:
    return project.get_dashboard(object_id).get_settings().get_raw()


def _insight(project, object_id: str, version_id: str) -> dict[str, Any]:
    return project.get_insight(object_id).get_settings().get_raw()


def _webapp(project, object_id: str, version_id: str) -> dict[str, Any]:
    return project.get_webapp(object_id).get_settings().get_raw()


def _knowledge_bank(project, object_id: str, version_id: str) -> dict[str, Any]:
    return project.get_knowledge_bank(object_id).get_settings().get_raw()


def _retrieval_augmented_llm(project, object_id: str, version_id: str) -> dict[str, Any]:
    return project.get_retrieval_augmented_llm(object_id).get_settings().get_raw()


def _agent_tool(project, object_id: str, version_id: str) -> dict[str, Any]:
    return project.get_agent_tool(object_id).get_settings().get_raw()


def _agent_review(project, object_id: str, version_id: str) -> dict[str, Any]:
    return project.get_agent_review(object_id).get_raw()


def _agent(project, object_id: str, version_id: str) -> dict[str, Any]:
    raw = project.get_agent(object_id).get_settings().get_raw()
    if not version_id:
        return raw
    for version in raw.get("versions", []):
        if version.get("versionId") == version_id:
            base = {key: value for key, value in raw.items() if key != "versions"}
            base["version"] = version
            return base
    available = [version.get("versionId") for version in raw.get("versions", [])]
    raise ValueError(
        f"Version '{version_id}' not found for agent '{object_id}'. "
        f"Available versions: {available}"
    )


def _semantic_model(project, object_id: str, version_id: str) -> dict[str, Any]:
    return project.get_semantic_model(object_id).get_version(version_id).get_settings().get_raw()


def _saved_model(project, object_id: str, version_id: str) -> dict[str, Any]:
    details = project.get_saved_model(object_id).get_version_details(version_id)
    return {
        "details_class": details.__class__.__name__,
        "snippet": details.get_raw_snippet(),
    }


def _ml_analysis(project, object_id: str, version_id: str) -> dict[str, Any]:
    analysis = project.get_analysis(object_id)
    task_ref = require_single_ml_task(analysis)
    mltask_id = task_ref["mlTaskId"]
    mltask = analysis.get_ml_task(mltask_id)
    return {
        "analysis_name": analysis.get_definition().get_raw().get("name"),
        "mltask_id": mltask_id,
        "mltask_settings": mltask.get_settings().get_raw(),
    }


def _evaluation_store(project, object_id: str, version_id: str) -> dict[str, Any]:
    return project.get_model_evaluation_store(object_id).get_settings().settings


# Closed enum -> resolver. Each resolver reuses the exact ``dataikuapi`` call the
# now-deleted narrow tool used, and returns the raw settings dict to place under
# ``settings`` in the response envelope.
_RESOLVERS: dict[str, Callable[[Any, str, str], dict[str, Any]]] = {
    "wiki_article": _wiki_article,
    "dashboard": _dashboard,
    "insight": _insight,
    "webapp": _webapp,
    "semantic_model": _semantic_model,
    "knowledge_bank": _knowledge_bank,
    "retrieval_augmented_llm": _retrieval_augmented_llm,
    "agent": _agent,
    "agent_tool": _agent_tool,
    "agent_review": _agent_review,
    "ml_analysis": _ml_analysis,
    "saved_model": _saved_model,
    "evaluation_store": _evaluation_store,
}
_OBJECT_TYPES = frozenset(_RESOLVERS)


def _bounded_settings(settings: Any) -> dict[str, Any]:
    """Return either ``{"settings": …}`` or a byte-bounded truncation envelope.

    The redacted settings are serialized; if the compact JSON fits under the
    ceiling it is returned parsed, otherwise the JSON text is clipped on a UTF-8
    boundary and returned as a string alongside ``truncated`` and byte counts, so
    the response is always bounded and never silently lies about completeness.
    """
    encoded = compact_json(settings).encode("utf-8")
    if len(encoded) <= MAX_SETTINGS_BYTES:
        return {"settings": settings}
    clipped = encoded[:MAX_SETTINGS_BYTES].decode("utf-8", errors="ignore")
    return {
        "truncated": True,
        "total_bytes": len(encoded),
        "returned_bytes": len(clipped.encode("utf-8")),
        "settings_json_truncated": clipped,
    }


@mcp.tool()
async def get_object_settings(
    project_key: str,
    object_type: str,
    object_id: str,
    ctx: Context,
    version_id: str = "",
) -> str:
    """Read the raw settings of one DSS object, for INDEPENDENT verification of
    Cobuild's work. One generic deep-read replacing the per-type settings tools.

    Cobuild's report is testimony, not evidence — this is the read path that lets
    you confirm it with your own eyes for the object types Cobuild builds but that
    have no other deep read. Secret-bearing keys are redacted and the payload is
    bounded to a hard byte ceiling. For a live/runtime view (a WebApp's backend
    state, an agent review's run outcomes) the raw settings won't show it — fall
    back to a read-only Cobuild turn for that.

    Object types with their own dedicated deep reads (datasets, recipes,
    scenarios, connections, folders, jobs, projects) are NOT served here; use
    those tools.

    Args:
        object_type: One of wiki_article, dashboard, insight, webapp,
            semantic_model, knowledge_bank, retrieval_augmented_llm, agent,
            agent_tool, agent_review, ml_analysis, saved_model, evaluation_store.
        object_id: The object's stable id within the project.
        version_id: Required for saved_model and semantic_model (their deep read
            is a per-version detail). Optional for agent (defaults to the full
            multi-version settings; when given, returns just that version). Must
            be empty for every other type.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    object_type = _require_allowed_value(
        _require_non_empty_string(object_type, "object_type").lower(),
        "object_type",
        _OBJECT_TYPES,
    )
    object_id = _require_non_empty_string(object_id, "object_id")
    version_id = version_id.strip() if isinstance(version_id, str) else ""

    if version_id and object_type not in _VERSIONED_TYPES:
        raise ValueError(
            f"'version_id' does not apply to object_type '{object_type}'. It is "
            f"used only by: {sorted(_VERSIONED_TYPES)}."
        )
    if object_type in _VERSION_REQUIRED_TYPES and not version_id:
        raise ValueError(
            f"object_type '{object_type}' requires 'version_id' (its deep read is "
            f"a per-version detail). Discover versions with the matching list tool."
        )

    await ctx.info(
        f"Reading {object_type} settings for '{object_id}' in {project_key}..."
    )

    resolver = _RESOLVERS[object_type]

    def _run() -> dict[str, Any]:
        project = get_dss_client().get_project(project_key)
        try:
            settings = resolver(project, object_id, version_id)
        except DataikuException as exc:
            raise ValueError(
                f"Could not read {object_type} '{object_id}' in project "
                f"'{project_key}': {exc}"
            ) from exc
        redacted = redact_sensitive_values(settings, VARIABLE_REDACTION)
        result: dict[str, Any] = {
            "object_type": object_type,
            "object_id": object_id,
        }
        if version_id:
            result["version_id"] = version_id
        result.update(_bounded_settings(redacted))
        return result

    return compact_json(await run_blocking(_run))
