"""LLM, Knowledge Bank, and Retrieval-Augmented LLM inspection tools."""

from typing import Any

from fastmcp import Context

from .. import mcp
from .utils.async_executor import run_blocking
from .utils.auth import get_dss_client
from .utils.serialization import columnar, compact_json
from .utils.validation import (
    require_allowed_value as _require_allowed_value,
    require_non_empty_string as _require_non_empty_string,
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


def _serialize_llm_item(
    item: dict[str, Any], available_purposes: list[str]
) -> dict[str, Any]:
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
    """List DSS-managed LLMs available in the project."""
    project_key = _require_non_empty_string(project_key, "project_key")
    purpose = _require_non_empty_string(purpose, "purpose").upper()
    normalized_purpose = (
        None
        if purpose == "ALL"
        else _require_allowed_value(purpose, "purpose", LLM_PURPOSES)
    )
    await ctx.info(f"Listing LLMs in {project_key} for purpose={purpose}...")
    llms = await run_blocking(_collect_llms, project_key, normalized_purpose)
    return compact_json(
        {
            "purpose": purpose,
            "llms": columnar(
                llms,
                ["id", "name", "type", "connection", "model", "available_purposes"],
            ),
        }
    )


@mcp.tool()
async def get_llm_info(project_key: str, llm_id: str, ctx: Context) -> str:
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
    return compact_json({"llm": llm, "detail_source": "dss_list_llms_payload"})


@mcp.tool()
async def list_knowledge_banks(project_key: str, ctx: Context) -> str:
    """List the Knowledge Banks in the project."""
    project_key = _require_non_empty_string(project_key, "project_key")
    await ctx.info(f"Listing Knowledge Banks in {project_key}...")
    items = await run_blocking(
        lambda: get_dss_client().get_project(project_key).list_knowledge_banks()
    )
    return compact_json({"knowledge_banks": [dict(item) for item in items]})


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
    """Search for documents in a Knowledge Bank."""
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
        raise ValueError(
            "'similarity_threshold' must be a float, typically between 0 and 1"
        )
    if not isinstance(mmr_factor, (int, float)) or not 0 <= float(mmr_factor) <= 1:
        raise ValueError("'mmr_factor' must be a float between 0 and 1")

    await ctx.info(
        f"Searching Knowledge Bank {knowledge_bank_id} in {project_key} "
        f"with search_type={search_type}..."
    )

    def _run():
        kb = (
            get_dss_client()
            .get_project(project_key)
            .get_knowledge_bank(knowledge_bank_id)
        )
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
            {"text": doc.text, "score": doc.score, "metadata": doc.metadata}
            for doc in result.documents
        ]

    documents = await run_blocking(_run)
    return compact_json(
        {
            "query": query,
            "search_type": search_type,
            "documents": columnar(documents, ["text", "score", "metadata"]),
        }
    )


def _serialize_rag_llm_item(raw: dict) -> dict:
    active_version_id = raw.get("activeVersion", "")
    versions = raw.get("versions", [])
    active_version = next(
        (
            version
            for version in versions
            if version.get("versionId") == active_version_id
        ),
        None,
    )
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
        lambda: (
            get_dss_client().get_project(project_key).list_retrieval_augmented_llms()
        )
    )
    rag_llms = [_serialize_rag_llm_item(dict(item)) for item in items]
    return compact_json(
        {
            "retrieval_augmented_llms": columnar(
                rag_llms,
                ["id", "active_version", "llm_id", "knowledge_bank_ref", "tags"],
            )
        }
    )


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
