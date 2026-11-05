## v0.9.0 (2026-11-05)

### Feat

- **setup**: add connection management form
- **plugins**: support Git sources and guide plugin development
- **plugins**: restore installation and managed environment setup
- **tools**: enforce instance-type policies
- **config**: accept Govern instance types
- **config**: require explicit Dataiku instance types
- **plugins**: separate GitHub Copilot manifests
- **plugins**: support GitHub Copilot CLI

### Fix

- The Claude Code plugin is now `headless`. Existing claude.ai installs need no action. If an existing Claude Code install reports “not found”, install it once with `/plugin install headless@dataiku`. Codex, Cursor, Copilot, and CoCo retain `dataiku-headless`.
- The HTTP plugin remains separate as `headless-http`, with server key `dku` and a rename map for existing `dataiku-headless-http` installations.
- **datasets**: verify metric computation before claiming freshness
- **datasets**: recompute dataset metrics before reading them
- **tls**: trust operating system certificate authorities (#204)
- **plugins**: align client identities and marketplace catalogs
- **plugins**: align Codex plugin and agent marketplace identity
- **setup**: improve connection errors and saved key display
- **tls**: upgrade truststore to 0.10.5
- **setup**: show underlying connection test errors
- **instances**: expose connection errors for setup diagnosis
- **tls**: trust operating system certificate authorities
- resolve Copilot plugin conflicts with release/0.9.0
- **plugins**: migrate shortened plugin names safely
- **mcp**: shorten plugin and tool names for Bedrock
- resolve instance policy conflicts with release/0.9.0
- **setup**: name saved Dataiku instances consistently
- **setup**: close connection manager when startup is cancelled
- **runtime**: declare the SDK six dependency
- **setup**: preserve connection selection and close cancelled setup
- **plugins**: preserve updates after rebuild exceptions
- **jobs**: preserve progress in plugin future receipts
- **runtime**: declare the SDK six requirement
- **plugins**: verify Git targets and preserve safe recovery
- **plugins**: allow store sources over HTTP and mark env setup additive
- **plugins**: stop failed-build hint from promising a rebuild fixes desc.json
- **plugins**: make plugin code-env recovery work against real futures
- **config**: migrate stdio profiles missing instance types
- **config**: reconcile instance types with Code Studio authentication

### Refactor

- **tools**: shorten RAG LLM listing tool name
- **setup**: simplify connection rendering and guidance
- **tools**: clarify instance policies and defer product support
- **plugins**: fold single-use helpers into their callers
- **validation**: keep general-purpose helpers first
- **plugins**: keep Git updates on DSS
- **plugins**: reuse the interpreter Literal and tidy plugin docs
- **plugins**: trim response hints and comments to what agents act on
- **plugins**: simplify code-env setup, its guide, and install tests

## v0.8.0 (2026-10-08)

### Feat

- add instance types (#176)
- **auth**: support Code Studio API ticket authentication (#171)

### Fix

- **auth**: tag SDK requests with headless application header (#172)

## v0.7.0 (2026-09-30)

### Feat

- **plugins**: add Cursor-native manifest (#164)
- **projects**: support Cobuild instructions in project settings (#162)
- **coco**: added plugin.json for coco support (#160)
- **tools**: configure container execution settings (#140)

### Fix

- **libraries**: place Python source under /python/ by convention (#161)

## v0.6.0 (2026-09-21)

### Feat

- **mcp**: add HTTP JWT delegation (#125)
- **plugins**: manage installed instance plugins (#138)
- **tools**: add titles, intent descriptions, and annotations to inspection, data, admin, and execution tools (#146–#149)
- **jobs**: add abort_job tool to stop a running Dataiku job (#144)
- **cobuild**: add tool titles, intent descriptions, and annotations (#139)
- **setup**: warm the uv runtime before first server launch (#136)
- **cobuild**: return the project UI URL in Cobuild payloads (#133)

### Fix

- **plugins**: support Claude-hosted uploads (#153)
- **onboarding**: handle "discovered" but bad credentials better (#143)
- **cobuild**: add the trailing slash to the project Flow URL (#145)

## v0.5.0 (2026-09-02)

### Feat

- **instances**: report the active Dataiku instance version (#135)

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
