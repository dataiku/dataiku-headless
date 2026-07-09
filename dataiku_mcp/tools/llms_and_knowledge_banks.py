"""LLM, Knowledge Bank, and Retrieval-Augmented LLM project-object tools."""

from typing import Any

from fastmcp import Context

from .. import config, mcp
from .jobs import (
    DEFAULT_WAIT_TIMEOUT_SECONDS,
    VALID_JOB_TYPES,
    _wait_for_job_result,
)
from .utils.async_executor import run_blocking
from .utils.serialization import columnar, compact_json
from .utils.auth import get_dss_client
from .utils.parsing import coerce_json_object as _coerce_json_object
from .utils.validation import (
    require_allowed_value as _require_allowed_value,
)
from .utils.validation import (
    require_non_empty_string as _require_non_empty_string,
)
from .utils.validation import (
    require_positive_int as _require_positive_int,
)

LLM_PURPOSES = {
    "GENERIC_COMPLETION",
    "TEXT_EMBEDDING_EXTRACTION",
    "IMAGE_EMBEDDING_EXTRACTION",
    "RERANKING",
    "IMAGE_GENERATION",
}

KB_SEARCH_TYPES = {
    "SIMILARITY",
    "SIMILARITY_THRESHOLD",
    "MMR",
    "HYBRID",
}


def _serialize_llm_item(item: dict[str, Any], available_purposes: list[str]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "name": item.get("friendlyNameShort", ""),
        "type": item.get("type"),
        "connection": item.get("connection"),
        "model": item.get("model"),
        "available_purposes": available_purposes,
    }


def _list_llm_items(project_key: str, purpose: str) -> list:
    project = get_dss_client().get_project(project_key)
    return project.list_llms(purpose=purpose)


def _collect_llms(project_key: str, purpose: str | None) -> list[dict[str, Any]]:
    purposes = [purpose] if purpose is not None else sorted(LLM_PURPOSES)

    items_by_id: dict[str, dict[str, Any]] = {}
    purposes_by_id: dict[str, set[str]] = {}

    for current_purpose in purposes:
        for item in _list_llm_items(project_key, current_purpose):
            llm_id = item.get("id")
            if not isinstance(llm_id, str) or not llm_id.strip():
                continue
            if llm_id not in items_by_id:
                items_by_id[llm_id] = dict(item)
                purposes_by_id[llm_id] = set()
            purposes_by_id[llm_id].add(current_purpose)

    return [
        _serialize_llm_item(items_by_id[llm_id], sorted(purposes_by_id[llm_id]))
        for llm_id in sorted(items_by_id)
    ]


@mcp.tool()
async def list_llms(
    project_key: str,
    ctx: Context,
    purpose: str = "ALL",
) -> str:
    """List the DSS-managed LLMs available in the project with compact discovery metadata.

    Args:
        purpose: Filter by purpose; one of ALL, GENERIC_COMPLETION, TEXT_EMBEDDING_EXTRACTION, IMAGE_EMBEDDING_EXTRACTION, RERANKING, IMAGE_GENERATION
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    purpose = _require_non_empty_string(purpose, "purpose").upper()
    normalized_purpose = None if purpose == "ALL" else _require_allowed_value(
        purpose, "purpose", LLM_PURPOSES
    )

    await ctx.info(
        f"Listing LLMs in {project_key} for purpose={purpose}..."
    )

    llms = await run_blocking(_collect_llms, project_key, normalized_purpose)

    return compact_json({
            "purpose": purpose,
            "llms": columnar(
                llms,
                ["id", "name", "type", "connection", "model", "available_purposes"],
            ),
        })


@mcp.tool()
async def get_llm_info(
    project_key: str,
    llm_id: str,
    ctx: Context,
) -> str:
    """Get the full metadata payload for a DSS-managed LLM visible in the project."""
    project_key = _require_non_empty_string(project_key, "project_key")
    llm_id = _require_non_empty_string(llm_id, "llm_id")

    await ctx.info(f"Loading LLM {llm_id} in {project_key}...")

    def _get() -> dict[str, Any]:
        payload: dict[str, Any] | None = None
        available_purposes: set[str] = set()

        for purpose in sorted(LLM_PURPOSES):
            for item in _list_llm_items(project_key, purpose):
                if item.get("id") != llm_id:
                    continue
                if payload is None:
                    payload = dict(item)
                available_purposes.add(purpose)

        if payload is None:
            raise ValueError(
                f"LLM '{llm_id}' was not found in project '{project_key}'. "
                "Use list_llms first to discover a valid id."
            )

        payload["available_purposes"] = sorted(available_purposes)
        return payload

    llm = await run_blocking(_get)

    return compact_json({
            "llm": llm,
            "detail_source": "dss_list_llms_payload",
        })


@mcp.tool()
async def list_knowledge_banks(project_key: str, ctx: Context) -> str:
    """List the Knowledge Banks in the project."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing Knowledge Banks in {project_key}...")

    items = await run_blocking(
        lambda: get_dss_client().get_project(project_key).list_knowledge_banks()
    )

    knowledge_banks = [dict(item) for item in items]

    return compact_json({
            "knowledge_banks": knowledge_banks,
        })


@mcp.tool()
async def get_knowledge_bank_settings(
    project_key: str,
    knowledge_bank_id: str,
    ctx: Context,
) -> str:
    """Get the full settings dict for a Knowledge Bank."""
    project_key = _require_non_empty_string(project_key, "project_key")
    knowledge_bank_id = _require_non_empty_string(
        knowledge_bank_id, "knowledge_bank_id"
    )
    await ctx.info(
        f"Loading settings for Knowledge Bank {knowledge_bank_id} in {project_key}..."
    )

    raw = await run_blocking(
        lambda: (
            get_dss_client()
            .get_project(project_key)
            .get_knowledge_bank(knowledge_bank_id)
            .get_settings()
            .get_raw()
        )
    )

    return compact_json(raw)


@mcp.tool()
async def build_knowledge_bank(
    project_key: str,
    knowledge_bank_id: str,
    ctx: Context,
    wait_for_completion: bool = True,
    job_type: str = "NON_RECURSIVE_FORCED_BUILD",
    timeout_seconds: int = DEFAULT_WAIT_TIMEOUT_SECONDS,
) -> str:
    """Build an existing Knowledge Bank as a DSS job.

    Args:
        wait_for_completion: If true, wait for the job to finish; if false, start it and return the job ID
        job_type: One of NON_RECURSIVE_FORCED_BUILD, RECURSIVE_BUILD, RECURSIVE_FORCED_BUILD
        timeout_seconds: Max time to wait before returning in-progress job state
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    knowledge_bank_id = _require_non_empty_string(
        knowledge_bank_id, "knowledge_bank_id"
    )
    job_type = _require_allowed_value(job_type, "job_type", VALID_JOB_TYPES)
    timeout_seconds = _require_positive_int(timeout_seconds, "timeout_seconds")

    await ctx.info(
        f"Building Knowledge Bank {knowledge_bank_id} in {project_key} "
        f"({job_type}, wait_for_completion={wait_for_completion})..."
    )

    def _run():
        kb = get_dss_client().get_project(project_key).get_knowledge_bank(knowledge_bank_id)
        return kb.build(job_type=job_type, wait=False)

    job = await run_blocking(_run)

    if not wait_for_completion:
        return compact_json({
                "status": "knowledge_bank_build_started",
                "job_type": job_type,
                "job_id": job.id,
                "hint": (
                    "Use get_job_status(project_key, job_id) for lightweight DSS job "
                    "status polling."
                ),
            })

    timed_out, status_summary = await _wait_for_job_result(
        project_key,
        job,
        timeout_seconds,
    )
    if timed_out:
        return compact_json({
                "status": "knowledge_bank_build_still_running",
                "job_type": job_type,
                "job_id": job.id,
                "timeout_seconds": timeout_seconds,
                "status_summary": status_summary,
                "hint": (
                    "Do not start another build for this Knowledge Bank while this job "
                    "is still running. Use wait_for_job(project_key, job_id, "
                    "timeout_seconds=...) or get_job_status(project_key, job_id). Add "
                    "full=true only when you need more detail, or use "
                    "get_job_log(project_key, job_id) for logs."
                ),
            })

    top_level_status = "knowledge_bank_build_completed"
    if status_summary["state"] in {"FAILED", "ABORTED"}:
        top_level_status = "knowledge_bank_build_completed_with_errors"

    return compact_json({
            "status": top_level_status,
            "status_summary": status_summary,
            "job_type": job_type,
            "job_id": job.id,
            "timeout_seconds": timeout_seconds,
        })


@mcp.tool()
async def delete_knowledge_bank(
    project_key: str,
    knowledge_bank_id: str,
    ctx: Context,
) -> str:
    """Delete a Knowledge Bank from a project. Requires explicit user intent."""
    project_key = _require_non_empty_string(project_key, "project_key")
    knowledge_bank_id = _require_non_empty_string(
        knowledge_bank_id, "knowledge_bank_id"
    )

    await ctx.info(
        f"Deleting Knowledge Bank {knowledge_bank_id} in {project_key}..."
    )

    def _run():
        kb = get_dss_client().get_project(project_key).get_knowledge_bank(knowledge_bank_id)
        kb.delete()
        return {}

    return compact_json(await run_blocking(_run))


@mcp.tool()
async def search_knowledge_bank(
    project_key: str,
    knowledge_bank_id: str,
    query: str,
    ctx: Context,
    max_documents: int = 10,
    search_type: str = "SIMILARITY",
    similarity_threshold: float = 0.5,
    mmr_documents_count: int = 20,
    mmr_factor: float = 0.25,
    hybrid_use_advanced_reranking: bool = False,
    hybrid_rrf_rank_constant: int = 60,
    hybrid_rrf_rank_window_size: int = 4,
) -> str:
    """Search for documents in a Knowledge Bank. MMR and HYBRID search types are not supported by every vector store.

    Args:
        query: Search query text
        max_documents: Maximum number of documents to return
        search_type: One of SIMILARITY, SIMILARITY_THRESHOLD, MMR, HYBRID
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    knowledge_bank_id = _require_non_empty_string(
        knowledge_bank_id, "knowledge_bank_id"
    )
    query = _require_non_empty_string(query, "query")
    max_documents = _require_positive_int(max_documents, "max_documents")
    search_type = _require_allowed_value(
        _require_non_empty_string(search_type, "search_type").upper(),
        "search_type",
        KB_SEARCH_TYPES,
    )
    mmr_documents_count = _require_positive_int(
        mmr_documents_count, "mmr_documents_count"
    )
    hybrid_rrf_rank_constant = _require_positive_int(
        hybrid_rrf_rank_constant, "hybrid_rrf_rank_constant"
    )
    hybrid_rrf_rank_window_size = _require_positive_int(
        hybrid_rrf_rank_window_size, "hybrid_rrf_rank_window_size"
    )

    if not isinstance(similarity_threshold, (int, float)):
        raise ValueError("'similarity_threshold' must be a float, typically between 0 and 1")
    if not isinstance(mmr_factor, (int, float)) or not 0 <= float(mmr_factor) <= 1:
        raise ValueError("'mmr_factor' must be a float between 0 and 1")

    await ctx.info(
        f"Searching Knowledge Bank {knowledge_bank_id} in {project_key} "
        f"with search_type={search_type}..."
    )

    def _run():
        kb = get_dss_client().get_project(project_key).get_knowledge_bank(knowledge_bank_id)
        result = kb.search(
            query=query,
            max_documents=max_documents,
            search_type=search_type,
            similarity_threshold=float(similarity_threshold),
            mmr_documents_count=mmr_documents_count,
            mmr_factor=float(mmr_factor),
            hybrid_use_advanced_reranking=hybrid_use_advanced_reranking,
            hybrid_rrf_rank_constant=hybrid_rrf_rank_constant,
            hybrid_rrf_rank_window_size=hybrid_rrf_rank_window_size,
        )
        return [
            {
                "text": doc.text,
                "score": doc.score,
                "metadata": doc.metadata,
            }
            for doc in result.documents
        ]

    documents = await run_blocking(_run)

    return compact_json({
            "query": query,
            "search_type": search_type,
            "documents": columnar(documents, ["text", "score", "metadata"]),
        })


def _serialize_rag_llm_item(raw: dict) -> dict:
    active_version_id = raw.get("activeVersion", "")
    versions = raw.get("versions", [])
    active_version = next((v for v in versions if v.get("versionId") == active_version_id), None)
    rag_settings = (active_version or {}).get("ragllmSettings", {})
    return {
        "id": raw.get("id", ""),
        "active_version": active_version_id,
        "llm_id": rag_settings.get("llmId", ""),
        "knowledge_bank_ref": rag_settings.get("kbRef", ""),
        "tags": raw.get("tags", []),
    }


@mcp.tool()
async def list_retrieval_augmented_llms(project_key: str, ctx: Context) -> str:
    """List the Retrieval-Augmented LLMs in the project."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing Retrieval-Augmented LLMs in {project_key}...")

    items = await run_blocking(
        lambda: get_dss_client().get_project(project_key).list_retrieval_augmented_llms()
    )
    retrieval_augmented_llms = [_serialize_rag_llm_item(dict(item)) for item in items]

    return compact_json({
            "retrieval_augmented_llms": columnar(
                retrieval_augmented_llms,
                ["id", "active_version", "llm_id", "knowledge_bank_ref", "tags"],
            ),
        })


@mcp.tool()
async def get_retrieval_augmented_llm_settings(
    project_key: str,
    retrieval_augmented_llm_id: str,
    ctx: Context,
) -> str:
    """Get the full live settings dict for a Retrieval-Augmented LLM."""
    project_key = _require_non_empty_string(project_key, "project_key")
    retrieval_augmented_llm_id = _require_non_empty_string(
        retrieval_augmented_llm_id, "retrieval_augmented_llm_id"
    )
    await ctx.info(
        f"Loading Retrieval-Augmented LLM {retrieval_augmented_llm_id} in {project_key}..."
    )

    raw = await run_blocking(
        lambda: (
            get_dss_client()
            .get_project(project_key)
            .get_retrieval_augmented_llm(retrieval_augmented_llm_id)
            .get_settings()
            .get_raw()
        )
    )

    return compact_json(raw)


@mcp.tool()
async def create_retrieval_augmented_llm(
    project_key: str,
    name: str,
    knowledge_bank_ref: str,
    ctx: Context,
    llm_id: str | None = None,
) -> str:
    """Create a new Retrieval-Augmented LLM in the project.

    Args:
        name: Display name (uniqueness not required)
        knowledge_bank_ref: Identifier of the backing Knowledge Bank
        llm_id: Identifier of the LLM used for the RAG process
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    name = _require_non_empty_string(name, "name")
    knowledge_bank_ref = _require_non_empty_string(
        knowledge_bank_ref, "knowledge_bank_ref"
    )
    llm_id = llm_id or config.get_current_instance().default_llm
    llm_id = _require_non_empty_string(llm_id, "llm_id")

    await ctx.info(
        f"Creating Retrieval-Augmented LLM '{name}' in {project_key}..."
    )

    def _run():
        project = get_dss_client().get_project(project_key)
        rag_llm = project.create_retrieval_augmented_llm(
            name=name,
            knowledge_bank_ref=knowledge_bank_ref,
            llm_id=llm_id,
        )
        settings = rag_llm.get_settings().get_raw()
        return {
            "id": rag_llm.id,
            "settings": settings,
        }

    result = await run_blocking(_run)

    return compact_json({
            "retrieval_augmented_llm_id": result["id"],
            "name": name,
            "llm_id": llm_id,
            "settings": result["settings"],
        })


@mcp.tool()
async def set_retrieval_augmented_llm_settings(
    project_key: str,
    retrieval_augmented_llm_id: str,
    new_settings,
    ctx: Context,
) -> str:
    """Set the full settings of a Retrieval-Augmented LLM.

    Args:
        new_settings: A modified version of the object returned by get_retrieval_augmented_llm_settings
    """
    project_key = _require_non_empty_string(project_key, "project_key")
    retrieval_augmented_llm_id = _require_non_empty_string(
        retrieval_augmented_llm_id, "retrieval_augmented_llm_id"
    )
    settings_obj = _coerce_json_object(new_settings, "new_settings")

    await ctx.info(
        f"Updating Retrieval-Augmented LLM {retrieval_augmented_llm_id} in {project_key}..."
    )

    def _run():
        rag_llm = (
            get_dss_client()
            .get_project(project_key)
            .get_retrieval_augmented_llm(retrieval_augmented_llm_id)
        )
        current = rag_llm.get_settings()
        raw = current.get_raw()
        raw.clear()
        raw.update(settings_obj)
        current.save()

    await run_blocking(_run)

    return compact_json({})
