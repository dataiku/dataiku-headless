"""One generic, independent settings read over the objects Cobuild builds.

``get_object_settings`` is the single deep read for the 13 object families that
have no other dedicated reader. It dispatches through a closed ``object_type``
enum to the same ``dataikuapi`` accessors each narrow reader once used and returns
the same evidence: usually the raw settings dictionary, with purpose-shaped
envelopes for wiki articles, ML analyses, model versions, and evaluation stores.

Runtime evidence is deliberately outside this read: it returns saved settings, not
live state. There are no dedicated runtime readers for a WebApp's live backend or an
agent review's runs/results — obtain that proof by delegating a read-only Cobuild
turn. Discover the ``object_id`` for the families with no ``list_*`` tool from
``get_project_overview``'s ``object_inventory``. Datasets, recipes, scenarios,
connections, folders, jobs, and project metadata retain their dedicated deep reads.

Every result is recursively redacted by field name (the one shared redactor) and
the serialized settings blob is bounded to a hard byte ceiling.
"""

from __future__ import annotations

from typing import Any, Callable

from dataikuapi.utils import DataikuException
from fastmcp import Context

from .. import mcp
from .machine_learning.shared.common import (
    find_analysis_input_dataset,
    require_single_ml_task,
)
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.redaction import VARIABLE_REDACTION, redact_sensitive_values
from .utils.serialization import bounded_compact_json
from .utils.validation import (
    require_allowed_value as _require_allowed_value,
    require_non_empty_string as _require_non_empty_string,
)

# Hard server ceiling on the serialized settings blob. Raw settings dicts (an ML
# task's per-feature config, a structured agent's block graph) can be large; the
# read is always bounded so a single object can never return an unbounded
# payload. When the compact-JSON settings exceed this, the blob is clipped on a
# UTF-8 boundary and the response carries ``truncated: true`` with byte counts —
# a plain size-check-and-clip via ``bounded_compact_json`` (no binary search).
MAX_SETTINGS_BYTES = 1_000_000
MAX_ERROR_VERSION_SUGGESTIONS = 50

# ``version_id`` addresses a specific version of a versioned object. It is
# OPTIONAL for all three versioned types: given, it returns that version's
# detail; omitted, it returns a DISCOVERY payload (object metadata + the
# available version ids and active flags) so a caller with no separate list tool
# can find the version ids these deep reads take. It is rejected for every other
# type so a caller learns the argument is inert rather than silently ignored.
_VERSIONED_TYPES = frozenset({"saved_model", "semantic_model", "agent"})


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
    shown = available[:MAX_ERROR_VERSION_SUGGESTIONS]
    suffix = (
        f" (showing {len(shown)} of {len(available)})"
        if len(available) > len(shown)
        else ""
    )
    raise ValueError(
        f"Version '{version_id}' not found for agent '{object_id}'. "
        f"Available versions{suffix}: {shown}"
    )


def _semantic_model(project, object_id: str, version_id: str) -> dict[str, Any]:
    semantic_model = project.get_semantic_model(object_id)
    if not version_id:
        try:
            active_version_id = semantic_model.get_active_version_id()
        except Exception:  # SDK raises plain Exception when no active version
            active_version_id = None
        return {
            "discovery": True,
            "active_version_id": active_version_id,
            "version_ids": semantic_model.list_versions_ids(),
        }
    try:
        return semantic_model.get_version(version_id).get_settings().get_raw()
    except DataikuException:
        raise
    except Exception as exc:
        # The real semantic-model SDK raises a plain ``Exception`` (not
        # ``DataikuException``) for an unknown version. Normalize it to the same
        # clear ValueError the caller gets for every other bad-version path.
        raise ValueError(
            f"Version '{version_id}' not found for semantic_model '{object_id}' "
            f"({type(exc).__name__})"
        ) from exc


def _saved_model(project, object_id: str, version_id: str) -> dict[str, Any]:
    saved_model = project.get_saved_model(object_id)
    if not version_id:
        return {"discovery": True, "versions": saved_model.list_versions()}
    details = saved_model.get_version_details(version_id)
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
        "input_dataset": find_analysis_input_dataset(project, object_id),
        "mltask_id": mltask_id,
        "mltask_settings": mltask.get_settings().get_raw(),
    }


def _evaluation_store(project, object_id: str, version_id: str) -> dict[str, Any]:
    store = project.get_model_evaluation_store(object_id)
    store_settings = store.get_settings().settings
    evaluations: list[dict[str, Any]] = []
    for evaluation in store.list_evaluations():
        try:
            info = evaluation.get_full_info()
            evaluations.append(
                {
                    "evaluation_id": evaluation.evaluation_id,
                    "name": info.user_meta.get("name", ""),
                    "labels": info.user_meta.get("labels", []),
                    "created": info.creation_date,
                    "prediction_type": info.prediction_type,
                    "target_variable": info.target_variable,
                    "prediction_variable": info.prediction_variable,
                    "metrics": info.metrics,
                }
            )
        except Exception as exc:
            evaluations.append(
                {
                    "evaluation_id": evaluation.evaluation_id,
                    "error": f"read failed ({type(exc).__name__})",
                }
            )
    evaluations.sort(key=lambda item: item.get("created") or 0, reverse=True)
    return {"store_settings": store_settings, "evaluations": evaluations}


# Closed enum -> resolver. Each resolver reuses the exact ``dataikuapi`` call the
# corresponding narrow tool uses, and returns the type's deep-read payload to place
# under ``settings`` in the response envelope (usually the raw settings dict; see
# the module docstring for the few types with a purpose-shaped payload).
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


@mcp.tool()
async def get_object_settings(
    project_key: str,
    object_type: str,
    object_id: str,
    ctx: Context,
    version_id: str = "",
) -> str:
    """Read one DSS object's settings for independent verification of Cobuild.

    This generic read consolidates equivalent per-type settings calls. It returns
    saved settings, not live/runtime state such as a WebApp's running backend or an
    agent review's runs/results; for that proof, delegate a read-only Cobuild turn.

    Cobuild's report is testimony, not evidence — this is the read path that lets
    you confirm it with your own eyes for the object types Cobuild builds but that
    have no other deep read. Secret-bearing keys are redacted and the settings blob
    is bounded to a hard byte ceiling. Discover the ``object_id`` for the families
    with no ``list_*`` tool from ``get_project_overview``'s ``object_inventory``.

    Object types with their own dedicated deep reads (datasets, recipes,
    scenarios, connections, folders, jobs, projects) are NOT served here; use
    those tools.

    Args:
        object_type: One of wiki_article, dashboard, insight, webapp,
            semantic_model, knowledge_bank, retrieval_augmented_llm, agent,
            agent_tool, agent_review, ml_analysis, saved_model, evaluation_store.
        object_id: The object's stable id within the project.
        version_id: Optional for the versioned types (agent, saved_model,
            semantic_model). Given, it returns that version's detail. Omitted, it
            returns a DISCOVERY payload — object metadata plus the available
            version ids and active flags — so you can find the version to read
            without a separate list tool (agent still returns full multi-version
            settings when omitted). Must be empty for every other type.
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    object_type = _require_allowed_value(
        _require_non_empty_string(object_type, "object_type").lower(),
        "object_type",
        _OBJECT_TYPES,
    )
    object_id = _require_non_empty_string(object_id, "object_id")
    if not isinstance(version_id, str):
        raise ValueError("'version_id' must be a string")
    version_id = version_id.strip()

    if version_id and object_type not in _VERSIONED_TYPES:
        raise ValueError(
            f"'version_id' does not apply to object_type '{object_type}'. It is "
            f"used only by: {sorted(_VERSIONED_TYPES)}."
        )

    client = get_dss_client()
    await ctx.info(
        f"Reading {object_type} settings for '{object_id}' in {project_key}..."
    )

    resolver = _RESOLVERS[object_type]

    def _run() -> dict[str, Any]:
        project = client.get_project(project_key)
        try:
            settings = resolver(project, object_id, version_id)
        except DataikuException as exc:
            raise ValueError(
                f"Could not read {object_type} '{object_id}' in project "
                f"'{project_key}' ({type(exc).__name__})"
            ) from exc
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(
                f"Could not read {object_type} '{object_id}' in project "
                f"'{project_key}' ({type(exc).__name__})"
            ) from exc
        redacted = redact_sensitive_values(settings, VARIABLE_REDACTION)
        base: dict[str, Any] = {
            "object_type": object_type,
            "object_id": object_id,
        }
        if version_id:
            base["version_id"] = version_id
        return bounded_compact_json(
            {**base, "settings": redacted},
            MAX_SETTINGS_BYTES,
            payload_key="settings_json_truncated",
        )

    return await run_blocking(_run)
