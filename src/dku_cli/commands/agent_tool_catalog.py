"""Agent tool type metadata that is not exposed by the DSS public API."""

from __future__ import annotations

BUILTIN_TOOL_PARAM_KEYS: dict[str, list[str]] = {
    "DatasetRowLookup": [
        "datasetRef",
        "datasetSmartName",
        "retrievalMode",
        "maxRecords",
        "datasetInteractionUserMode",
    ],
    "DatasetRowAppend": [
        "datasetRef",
        "datasetSmartName",
        "datasetInteractionUserMode",
    ],
    "VectorStoreSearch": ["knowledgeBankRef"],
    "LLMMeshLLMQuery": ["llmId"],
    "ClassicalPredictionModelPredict": ["smRef"],
    "ApiEndpoint": [],
    "ImageGeneration": ["nbImagesToGenerate", "imageHandlingMode"],
    "GenerateArtifact": ["templateType", "outputFormat", "variables"],
}
