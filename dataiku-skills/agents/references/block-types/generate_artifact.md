---
name: block-generate-artifact-reference
description: "Param matrix and canonical example for the GENERATE_ARTIFACT block."
---

# GENERATE_ARTIFACT Block

Renders a template into an artifact (a downloadable/viewable attachment in the chat). Supports text/markdown templates and Word document templates.

## Param Matrix

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `id` | yes | string | Unique block identifier |
| `type` | yes | `"GENERATE_ARTIFACT"` | |
| `templateType` | yes | string | `"JINJA"`, `"CEL_EXPANSION"`, or `"DOCX_JINJA"` |
| `template` | yes | string | Template content (JINJA/CEL_EXPANSION) |
| `managedFolderRef` | DOCX_JINJA only | string | Managed folder ID containing the `.docx` template |
| `templateFilename` | DOCX_JINJA only | string | Filename of the `.docx` template within the folder |
| `outputFormat` | no | string | `"TEXT"`, `"MARKDOWN"`, `"DOCX"`, or `"PDF"` |
| `outputManagedFolderRef` | DOCX_JINJA only | string | Managed folder ID where the output file is saved |
| `outputFilename` | DOCX_JINJA only | string | Filename for the generated output file |
| `nextBlock` | yes* | string | Next block |

## Template Types

| Type | Use when |
|------|---------|
| `CEL_EXPANSION` | Plain text with `${state.key}` interpolation — simplest |
| `JINJA` | Markdown/text with full Jinja2: `{{ state.key }}`, conditionals, loops |
| `DOCX_JINJA` | Word document template (`.docx`) with Jinja2 tags — outputs DOCX or PDF |

## Canonical Examples

### JINJA (markdown report)
```json
{
  "id": "generate_report",
  "type": "GENERATE_ARTIFACT",
  "templateType": "JINJA",
  "template": "# Offer Letter\n\n**Status:** {{ state.approval_status }}\n\n| Detail | Value |\n|--------|-------|\n| Rate | {{ state.interest_rate }} |",
  "outputFormat": "MARKDOWN",
  "nextBlock": "approve_output"
}
```

### DOCX_JINJA (Word document)
```json
{
  "id": "generate_contract",
  "type": "GENERATE_ARTIFACT",
  "templateType": "DOCX_JINJA",
  "managedFolderRef": "<template_folder_id>",
  "templateFilename": "contract_template.docx",
  "outputFormat": "PDF",
  "outputManagedFolderRef": "<output_folder_id>",
  "outputFilename": "generated_contract.pdf",
  "nextBlock": "send_output"
}
```

## Guardrails

1. **Jinja templates access state via `{{ state.key }}`** — state must have been set by an upstream block (`SET_STATE_ENTRIES`, `LLM_REQUEST` with `SAVE_TO_STATE`).
2. **DOCX_JINJA requires two managed folders** — one for the input template (`managedFolderRef` + `templateFilename`) and one for the output (`outputManagedFolderRef` + `outputFilename`). Both must exist before the block runs.
3. If dynamic content is needed but state can't be populated, use an `LLM_REQUEST` block with `streamOutput: true` instead.
4. Use `"outputFormat": "PDF"` with `DOCX_JINJA` to deliver a non-editable document.
