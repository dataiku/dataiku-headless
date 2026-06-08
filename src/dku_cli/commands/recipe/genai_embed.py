"""Embedding GenAI recipe commands."""

from __future__ import annotations

# ruff: noqa: F403,F405
from ._common import *

# ---------------------------------------------------------------------------
# GenAI recipe creation commands
# ---------------------------------------------------------------------------


@app.command("create-embed")
def create_embed(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str = typer.Option(..., "--input", "-i", help="Input dataset name"),
    output_kb: str = typer.Option(
        ..., "--output-kb", help="Output knowledge bank name or ID"
    ),
    embedding_llm: str = typer.Option(
        ...,
        "--embedding-llm",
        help="Embedding LLM ID (e.g. openai:text-embedding-3-small)",
    ),
    vector_store_type: str = typer.Option(
        "CHROMA", "--vector-store-type", help="Vector store type (default: CHROMA)"
    ),
    embed_column: str = typer.Option(
        None,
        "--embed-column",
        help="Column name to embed (required for dataset embedding). Maps to payload.knowledgeColumn.",
    ),
    metadata_col: list[str] | None = typer.Option(
        None,
        "--metadata-col",
        help=(
            "Carry-through column kept alongside each chunk for downstream RAG "
            "retrieval (source attribution). Maps to payload.metadataColumns[]. "
            "Repeatable: --metadata-col title --metadata-col url. "
            "Without this, retrieved chunks lose their source — RAG citations break."
        ),
    ),
    chunk_size: int | None = typer.Option(
        None,
        "--chunk-size",
        help="Chunk size in characters. Sets payload.chunkSizeCharacters.",
    ),
    chunk_overlap: int | None = typer.Option(
        None,
        "--chunk-overlap",
        help="Chunk overlap in characters. Sets payload.chunkOverlapCharacters.",
    ),
    document_splitting_mode: str | None = typer.Option(
        None,
        "--document-splitting-mode",
        help="How records are chunked. e.g. CHARACTERS_BASED (default), SECTIONS_BASED. Sets payload.documentSplittingMode.",
    ),
    vector_store_update_method: str | None = typer.Option(
        None,
        "--vector-store-update-method",
        help="How the vector store reacts to recipe re-runs (SMART_OVERWRITE, FULL_REBUILD, OVERWRITE). Sets payload.vectorStoreUpdateMethod.",
    ),
    clear_vector_store: bool = typer.Option(
        False,
        "--clear-vector-store",
        help="Wipe the vector store before the next build (one-shot). Sets payload.clearVectorStore=true.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an Embed Dataset recipe (embeds text columns into a Knowledge Bank).

    Use --embed-column to set which text column to embed. If omitted, you must
    configure the embedding column via set-definition before building the KB.

    The right field is `knowledgeColumn` (NOT `embedColumn`); the CLI handles
    that mapping. For source attribution in RAG retrieval, pass --metadata-col
    for every column you want carried alongside each chunk (title, url, etc.).
    """
    project_key = resolve_project(project)
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)
        builder = proj.new_recipe("nlp_llm_rag_embedding", recipe_name)
        builder.with_input(input_ds)

        # Check if KB already exists to avoid creating duplicates.
        # get_knowledge_bank() just instantiates a handle without an API call,
        # so we must use list_knowledge_banks() filtered by name.
        kb_list = proj.list_knowledge_banks()
        existing_kb = next((kb for kb in kb_list if kb.name == output_kb), None)

        if existing_kb:
            info(f"Using existing knowledge bank '{output_kb}' ({existing_kb.id})")
            builder.recipe_proto["outputs"]["knowledge_bank"] = {
                "items": [{"ref": existing_kb.id, "appendMode": False}]
            }
            builder.set_raw_mode()
        else:
            builder.with_output_knowledge_bank(
                output_kb, embedding_llm, vector_store_type
            )

        builder.build()

        any_payload_change = bool(
            embed_column
            or metadata_col
            or chunk_size is not None
            or chunk_overlap is not None
            or document_splitting_mode is not None
            or vector_store_update_method is not None
            or clear_vector_store
        )
        if any_payload_change:
            recipe_obj = proj.get_recipe(recipe_name)
            settings = recipe_obj.get_settings()
            payload = _get_recipe_payload(settings)
            if embed_column:
                payload["knowledgeColumn"] = embed_column
                info(f"Embedding column set to '{embed_column}'")
            if metadata_col:
                # DSS expects metadataColumns as objects, not bare strings. A
                # list of strings parses as JSON but the build job crashes with
                # "Expected BEGIN_OBJECT but was STRING".
                payload["metadataColumns"] = [{"column": c} for c in metadata_col]
                info(f"Metadata columns: {', '.join(metadata_col)}")
            if chunk_size is not None:
                payload["chunkSizeCharacters"] = chunk_size
            if chunk_overlap is not None:
                payload["chunkOverlapCharacters"] = chunk_overlap
            if document_splitting_mode is not None:
                payload["documentSplittingMode"] = document_splitting_mode
            if vector_store_update_method is not None:
                payload["vectorStoreUpdateMethod"] = vector_store_update_method
            if clear_vector_store:
                payload["clearVectorStore"] = True
            settings.save()
        if not embed_column:
            warn(
                "No --embed-column specified. Set the embedding column via "
                "'dku recipe set-definition' before building the knowledge bank."
            )

        success(f"Created embed recipe '{recipe_name}' in {project_key}")
    except Exception as e:
        handle_api_error(e)


@app.command("create-embed-docs")
def create_embed_docs(
    ctx: typer.Context,
    recipe_name: str = typer.Argument(help="Recipe name"),
    input_ds: str | None = typer.Option(
        None,
        "--input",
        "-i",
        help=(
            "Input FilesInFolder dataset wrapping a managed folder of documents "
            "(build one with `dku folder create-dataset`). Either --input or "
            "--input-folder is required."
        ),
    ),
    output_kb: str = typer.Option(
        ..., "--output-kb", help="Output knowledge bank name"
    ),
    embedding_llm: str = typer.Option(..., "--embedding-llm", help="Embedding LLM ID"),
    vlm: str = typer.Option(
        None,
        "--vlm",
        help="Vision LLM ID for document understanding (recommended when input is a folder of PDFs/images)",
    ),
    vector_store_type: str = typer.Option(
        "CHROMA", "--vector-store-type", help="Vector store type (default: CHROMA)"
    ),
    chunk_size: int | None = typer.Option(
        None,
        "--chunk-size",
        help="Chunk size in characters (default 3000). Sets payload.chunkSizeCharacters.",
    ),
    chunk_overlap: int | None = typer.Option(
        None,
        "--chunk-overlap",
        help="Chunk overlap in characters (default 120). Sets payload.chunkOverlapCharacters.",
    ),
    vector_store_update_method: str | None = typer.Option(
        None,
        "--vector-store-update-method",
        help="How the vector store reacts to recipe re-runs. Default: SMART_OVERWRITE (re-embed only changed docs). Other DSS values include FULL_REBUILD, OVERWRITE.",
    ),
    clear_vector_store: bool = typer.Option(
        False,
        "--clear-vector-store",
        help="Wipe the existing vector store contents before the next build (one-shot).",
    ),
    document_splitting_mode: str | None = typer.Option(
        None,
        "--document-splitting-mode",
        help="How documents are chunked. Default: CHARACTERS_BASED. DSS also exposes SECTIONS_BASED for structured PDFs.",
    ),
    extraction_mode: str | None = typer.Option(
        None,
        "--extraction-mode",
        help="Document extraction strategy. MANAGED_TEXT_ONLY (default — managed text-only) or CUSTOM_RULES (per-file-type rules in params.rules). DSS normalises any other value to CUSTOM_RULES — use that path when chaining a VLM, then template the rules with set-definition.",
    ),
    rule: str | None = typer.Option(
        None,
        "--rule",
        help=(
            "Custom-rules JSON: literal, @file.json, or '-' stdin. "
            "Sets params.rules[]. Implies extraction-mode CUSTOM_RULES if not set."
        ),
    ),
    input_folder: str | None = typer.Option(
        None,
        "--input-folder",
        help=(
            "Managed-folder ID to use as the recipe's main input — the canonical "
            "DSS 14.5+ folder→KB pattern, no FilesInFolder wrapper needed. If "
            "--input is ALSO given, the folder is attached as a 'documents' role "
            "(legacy DSS 14.4-compatible behavior)."
        ),
    ),
    output_images_folder: str | None = typer.Option(
        None,
        "--output-images-folder",
        help="Managed-folder ID where extracted page images are written (used by VLM/SECTIONS_BASED modes).",
    ),
    default_vlm: str | None = typer.Option(
        None,
        "--default-vlm",
        help="Default VLM ID applied across all rules (instead of per-rule). Sets payload.defaultVlmId.",
    ),
    rule_vlm: str | None = typer.Option(
        None,
        "--rule-vlm",
        help="VLM ID to inject as the vlmId on every rule (overrides any per-rule vlm). Useful with --rule @file.json.",
    ),
    rule_prompt: str | None = typer.Option(
        None,
        "--rule-prompt",
        help="Per-rule VLM prompt: literal, @file.txt, or '-' stdin. Injects 'prompt' into every rule.",
    ),
    ocr_engine: str | None = typer.Option(
        None,
        "--ocr-engine",
        help="OCR engine for scanned PDFs (TESSERACT, AZURE_DOCUMENT_INTELLIGENCE, etc.). Sets payload.ocrEngine.",
    ),
    ocr_languages: str | None = typer.Option(
        None,
        "--ocr-languages",
        help="Comma-separated OCR language codes (eng,fra,...). Sets payload.ocrLanguages[].",
    ),
    max_section_depth: int | None = typer.Option(
        None,
        "--max-section-depth",
        help="SECTIONS_BASED splitting: maximum nested heading depth. Sets payload.maxSectionDepth.",
    ),
    enable_image_classification_filtering: bool = typer.Option(
        False,
        "--enable-image-classification-filtering",
        help="Filter out images that don't pass classification threshold. Sets payload.enableImageClassificationFiltering=true.",
    ),
    project: str = typer.Option(None, "--project", "-P", help="Project key"),
) -> None:
    """Create an Embed Documents recipe (extracts + chunks + embeds documents into a KB).

    Two input shapes are supported:
      1. **Folder direct (canonical DSS 14.5+)**: pass --input-folder FOLDER_ID
         alone. The recipe reads the managed folder directly — no FilesInFolder
         wrapper needed. This is what CHATTERBOX and modern RAG flows use.
      2. **Legacy (DSS 14.4-)**: pass --input FILESINFOLDER_DATASET. Build the
         wrapper dataset first via `dku folder create-dataset`. If you ALSO
         pass --input-folder, the folder is attached as a 'documents' role on
         top of the main dataset.

    Exactly one of --input or --input-folder is required.

    Pass --vlm only when documents contain figures/tables that warrant a vision
    pass; for pure text the default text extractor is faster and cheaper.

    Knob mapping (recipe payload fields):
      --chunk-size                  → payload.chunkSizeCharacters
      --chunk-overlap               → payload.chunkOverlapCharacters
      --vector-store-update-method  → payload.vectorStoreUpdateMethod
      --clear-vector-store          → payload.clearVectorStore (one-shot wipe)
      --document-splitting-mode     → payload.documentSplittingMode
      --extraction-mode             → params.extractionMode

    Examples:
        # Canonical folder→KB pattern (DSS 14.5+)
        dku recipe create-embed-docs index_pdfs --input-folder PDF_FOLDER_ID \\
            --output-kb pdf_kb --embedding-llm openai:openai:text-embedding-3-small -P PROJ

        # Legacy FilesInFolder dataset path
        dku recipe create-embed-docs index_pdfs -i pdf_files \\
            --output-kb pdf_kb --embedding-llm openai:openai:text-embedding-3-small \\
            --chunk-size 1500 --chunk-overlap 150 \\
            --vector-store-update-method SMART_OVERWRITE -P PROJ
    """
    project_key = resolve_project(project)
    # Validate input shape: exactly one of --input or --input-folder.
    if not input_ds and not input_folder:
        exit_with_error(
            "create-embed-docs requires either --input or --input-folder.",
            code="missing_argument",
            details=[
                "Folder-direct (canonical):",
                f"  dku recipe create-embed-docs {recipe_name} --input-folder FOLDER_ID \\",
                "      --output-kb KB_NAME --embedding-llm LLM_ID -P PROJ",
                "",
                "Legacy FilesInFolder dataset:",
                f"  dku recipe create-embed-docs {recipe_name} -i FILES_DATASET \\",
                "      --output-kb KB_NAME --embedding-llm LLM_ID -P PROJ",
            ],
        )
    try:
        client = get_client_from_ctx(ctx)
        proj = client.get_project(project_key)

        # Folder-direct path needs to bypass the builder's required with_input.
        # When only --input-folder is provided we build a stub recipe via the
        # creator (so DSS provisions the KB output and creation_settings), then
        # rewire inputs.main to point at the folder. dataikuapi has no
        # with_input_folder() for embed_documents — this is the canonical
        # workaround for the gap.
        builder = proj.new_recipe("embed_documents", recipe_name)
        if input_ds:
            builder.with_input(input_ds)
        else:
            # No dataset input — use the folder ref directly so the creator's
            # input validation passes. We re-wire below.
            builder.with_input(input_folder)
        if vlm:
            builder.with_vlm(vlm)

        # Check if KB already exists to avoid creating duplicates
        kb_list = proj.list_knowledge_banks()
        existing_kb = next((kb for kb in kb_list if kb.name == output_kb), None)

        if existing_kb:
            info(f"Using existing knowledge bank '{output_kb}' ({existing_kb.id})")
            builder.recipe_proto["outputs"]["knowledge_bank"] = {
                "items": [{"ref": existing_kb.id, "appendMode": False}]
            }
            builder.set_raw_mode()
        else:
            builder.with_output_knowledge_bank(
                output_kb, embedding_llm, vector_store_type
            )

        builder.build()

        # Parse --rule body once (and infer extraction_mode if user didn't set it)
        parsed_rules: list[dict] | None = None
        effective_extraction_mode = extraction_mode
        if rule:
            rule_body = read_json_input(rule)
            if isinstance(rule_body, dict):
                parsed_rules = [rule_body]
            elif isinstance(rule_body, list):
                parsed_rules = rule_body
            else:
                exit_with_error(
                    "--rule must be a JSON object or array.",
                    code="invalid_argument",
                )
            if effective_extraction_mode is None:
                effective_extraction_mode = "CUSTOM_RULES"
        elif effective_extraction_mode is None:
            # An embed-docs recipe with no extractionMode at all NPEs at build
            # time ("allOtherFilesRule is null"). Default to the text-only
            # managed extraction the UI preselects.
            effective_extraction_mode = "MANAGED_TEXT_ONLY"

        # Inject rule-level overrides if requested
        rule_prompt_body = read_text_input(rule_prompt) if rule_prompt else None
        if parsed_rules and (rule_vlm or rule_prompt_body):
            for r in parsed_rules:
                if rule_vlm:
                    r["vlmId"] = rule_vlm
                if rule_prompt_body:
                    r["prompt"] = rule_prompt_body

        # Apply post-build payload knobs.
        any_payload_change = (
            chunk_size is not None
            or chunk_overlap is not None
            or vector_store_update_method is not None
            or clear_vector_store
            or document_splitting_mode is not None
            or default_vlm is not None
            or ocr_engine is not None
            or ocr_languages is not None
            or max_section_depth is not None
            or enable_image_classification_filtering
            or output_images_folder is not None
        )
        any_params_change = (
            effective_extraction_mode is not None or parsed_rules is not None
        )
        any_io_change = input_folder is not None or output_images_folder is not None
        # Folder-only path requires we rewrite inputs.main even when no other
        # knobs are set, otherwise the recipe stays wired to the (non-existent
        # or wrong) dataset placeholder.
        folder_only = bool(input_folder) and not input_ds
        if any_payload_change or any_params_change or any_io_change or folder_only:
            recipe_obj = proj.get_recipe(recipe_name)
            settings = recipe_obj.get_settings()
            if any_payload_change:
                payload = _get_recipe_payload(settings)
                if chunk_size is not None:
                    payload["chunkSizeCharacters"] = chunk_size
                if chunk_overlap is not None:
                    payload["chunkOverlapCharacters"] = chunk_overlap
                if vector_store_update_method is not None:
                    payload["vectorStoreUpdateMethod"] = vector_store_update_method
                if clear_vector_store:
                    payload["clearVectorStore"] = True
                if document_splitting_mode is not None:
                    payload["documentSplittingMode"] = document_splitting_mode
                if default_vlm is not None:
                    payload["defaultVlmId"] = default_vlm
                if ocr_engine is not None:
                    payload["ocrEngine"] = ocr_engine
                if ocr_languages is not None:
                    payload["ocrLanguages"] = [
                        lang.strip()
                        for lang in ocr_languages.split(",")
                        if lang.strip()
                    ]
                if max_section_depth is not None:
                    payload["maxSectionDepth"] = max_section_depth
                if enable_image_classification_filtering:
                    payload["enableImageClassificationFiltering"] = True
            if any_params_change:
                raw_def = settings.get_recipe_raw_definition()
                params = raw_def.setdefault("params", {})
                if effective_extraction_mode is not None:
                    params["extractionMode"] = effective_extraction_mode
                if parsed_rules is not None:
                    params["rules"] = parsed_rules
            if any_io_change or folder_only:
                raw_def = settings.get_recipe_raw_definition()
                if folder_only:
                    # Rewire main input to the folder (canonical DSS 14.5+
                    # folder→KB shape, what CHATTERBOX/ATU use).
                    inputs = raw_def.setdefault("inputs", {})
                    inputs["main"] = {"items": [{"ref": input_folder}]}
                elif input_folder is not None:
                    # Legacy path: attach folder as 'documents' role on top of
                    # the main FilesInFolder dataset input.
                    inputs = raw_def.setdefault("inputs", {})
                    inputs.setdefault("documents", {"items": []})["items"].append(
                        {"ref": input_folder}
                    )
                if output_images_folder is not None:
                    outputs = raw_def.setdefault("outputs", {})
                    outputs.setdefault("images", {"items": []})["items"].append(
                        {"ref": output_images_folder, "appendMode": False}
                    )
            settings.save()
        success(f"Created embed-docs recipe '{recipe_name}' in {project_key}")
    except Exception as e:
        handle_api_error(e)
