## v0.4.0 (2026-08-26)

### Feat

- **plugins**: add agent-assisted setup (#129)
- add project settings tools (#123)
- **code-envs**: filter environments by packages (#119)

### Fix

- redact encoded connection keys (#121)
- preserve existing upload datasets (#107)

## v0.3.0 (2026-08-19)

## v0.2.0 (2026-06-09)

### Feat

- **packaging**: publish as dataiku-headless bundling server, skills, and docs
- **mcp**: reconcile compaction stack #161–#165 onto main (lossless tool-result trimming) (#169)
- **flow**: emit get_flow_items as [ref, type] pairs (lossless) (#160)
- **recipes**: omit engineParams from get_recipe_settings by default (#159)
- **datasets**: compact get_dataset_profile (top-N arrays + compact JSON) (#157)
- **datasets**: columnar get_dataset_sample + lower default n_rows (#156)
- **datasets**: add include_schema opt-out to create_upload_dataset
- **join,datasets**: H2 FULL OUTER trap + sticky-bigint inference
- **recipes/prepare**: add MultiColumnFold + removeFoldedColumns param
- **recipes/prepare**: add MultiColumnByPrefixFold processor reference
- **recipes,datasets**: gotchas surfaced by migration testing
- **data-collections**: list collections and their objects
- **cross-project-sharing**: surface required permissions on forbidden
- **cross-project-sharing**: expose_objects tools as a dedicated module
- **jobs**: surface recipe_name and outputs per job activity
- **kb**: add delete_knowledge_bank tool
- **webapps**: add delete_webapp MCP tool and update skill docs

### Fix

- **mcp**: remove conflict markers shipped to main in datasets.py (#168)
- **datasets**: require upload connection
- **datasets**: correct create_upload_dataset connection docs (required)
- **ml**: honor full_reguess when target/prediction_type unchanged
- enable create_recipe for NLP recipe types (summarization, classification)
- **agents**: enforce build-run-inspect loop for dependent recipes
- **prepare**: quote numval column in flag formula example
- **prepare**: always quote column names in val/strval/numval examples
- **recipes**: support sql_query recipe code read/write/create
- **ml**: skip mltask.guess() no-ops and respect mutual exclusivity

### Refactor

- **mcp**: compact JSON for all tool results (shared compact_json helper) (#158)
- **datasets**: drop sticky-bigint bullet (Excel-specific, not general)
- **recipes**: trim gotcha clauses to rule-only
- **recipes**: PR140 review feedback — relocate/tighten gotchas
- **recipes,datasets**: caveman style — drop autodiscoverable + prose
- **cross-project-sharing**: rename expose/unexpose to share/unshare
- **cross-project-sharing**: drop item validation, document constraint in skill
- **cross-project-sharing**: simplify expose/unexpose to single target_project
