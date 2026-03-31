# DevKit Issues

Issues discovered during the `agent-skills-sva` plugin design and implementation session, focused on what to debug, fix, or update in the `$dataiku` and `$dku-cli` skills and supporting DevKit references.

## 1. Structured agent block packaging guidance is wrong or outdated

### Problem

The current `$dataiku` skill and references steered implementation toward the wrong custom block contract for DSS 14.4 structured agents:

- [`visual-agent-blocks.md`](/Users/youssefjouini/.agents/skills/dataiku/references/visual-agent-blocks.md) says:
  - folder: `python-blocks-graph-blocks/`
  - config keys: `kind`, `blockHandlerClass`, `blockHandlerModule`
  - runtime base class import: `from dataiku.agents.blocks import BlockHandler`
- [`plugin-structure.md`](/Users/youssefjouini/.agents/skills/dataiku/references/plugin-structure.md) says visual blocks use `python-blocks-graph-blocks/` and `block.py`

But the proven working plugin in this repo, [`plugins/agent-semantic-feedback`](/Users/youssefjouini/Desktop/Team/dataiku-cli/plugins/agent-semantic-feedback), uses:

- folder: `python-structured-agent-blocks/`
- config key: `pyClazzName`
- no per-block `block.py`
- runtime base class import: `from dataiku.llm.python.blocks_graph import BlockHandler, NextBlock`

This mismatch caused the runtime error:

```text
No class configured for custom block type ... known types: []
```

### Action

Update the `$dataiku` skill and references so structured-agent block guidance matches the working contract used by DSS 14.4 on this instance.

### Files to review

- [visual-agent-blocks.md](/Users/youssefjouini/.agents/skills/dataiku/references/visual-agent-blocks.md)
- [plugin-structure.md](/Users/youssefjouini/.agents/skills/dataiku/references/plugin-structure.md)
- [plugin-architecture.md](/Users/youssefjouini/.agents/skills/dataiku/references/plugin-architecture.md)
- [plugins/agent-semantic-feedback](/Users/youssefjouini/Desktop/Team/dataiku-cli/plugins/agent-semantic-feedback)

## 2. Structured agent block execution API guidance is wrong for this runtime

### Problem

The current `$dataiku` guidance teaches a block API shaped like:

```python
def process(self, context, input_data, block_definition):
```

with `context.messages.append(...)`.

The working plugin uses:

```python
def __init__(self, turn, sequence_context, block_config):
def process_stream(self, trace):
```

and appends messages through:

```python
self.sequence_context.generated_messages.append(...)
yield NextBlock(id=...)
```

Following the current doc caused stale references like `context.messages` inside our structured-agent block implementation.

### Action

Revise the `$dataiku` skill so it distinguishes:

- older/custom block guidance
- DSS 14.4 structured-agent block runtime guidance

and explicitly document the `turn` / `sequence_context` / `process_stream()` contract.

### Files to review

- [visual-agent-blocks.md](/Users/youssefjouini/.agents/skills/dataiku/references/visual-agent-blocks.md)
- [structured-agents.md](/Users/youssefjouini/.agents/skills/dataiku/references/structured-agents.md)
- [plugins/agent-semantic-feedback/python-lib/agent_semantic_feedback/detect_and_store_feedback.py](/Users/youssefjouini/Desktop/Team/dataiku-cli/plugins/agent-semantic-feedback/python-lib/agent_semantic_feedback/detect_and_store_feedback.py)
- [plugins/agent-semantic-feedback/python-lib/agent_semantic_feedback/use_feedback.py](/Users/youssefjouini/Desktop/Team/dataiku-cli/plugins/agent-semantic-feedback/python-lib/agent_semantic_feedback/use_feedback.py)

## 3. `$dataiku` should point to a local working structured-agent block example

### Problem

The skill tells the agent to browse references and official repos when unsure, but this repo already contains a working structured-agent block plugin:

- [`plugins/agent-semantic-feedback`](/Users/youssefjouini/Desktop/Team/dataiku-cli/plugins/agent-semantic-feedback)

That local example would have resolved the packaging/runtime ambiguity much faster than the current reference docs.

### Action

Add an explicit note to `$dataiku` and/or `visual-agent-blocks.md`:

- when building structured-agent blocks in this repo, first inspect `plugins/agent-semantic-feedback`

## 4. Parameter-type guidance needs stronger opinionated recommendations

### Problem

The raw parameter reference is correct, but the higher-level plugin guidance did not prevent avoidable UI mistakes:

- `managed_folder` should have been `MANAGED_FOLDER`, not `STRING`
- `llm_id` should have been `LLM`, not `STRING`
- manual multi-choice skills should have been `MULTISELECT`, not `STRINGS`

In practice:

- `STRINGS` rendered as a free-form tag input, not a dropdown
- `MULTISELECT` is the right multi-choice control
- `MANAGED_FOLDER` and `LLM` give the desired platform-native selectors

### Action

Update `$dataiku` plugin guidance to add an explicit section:

- use semantic parameter types first
- avoid raw `STRING` when a platform-native selector exists
- use `MULTISELECT` rather than `STRINGS` for bounded selectable values

### Files to review

- [parameters.md](/Users/youssefjouini/.agents/skills/dataiku/references/parameters.md)
- [scaffolding.md](/Users/youssefjouini/.agents/skills/dataiku/references/scaffolding.md)
- [plugin-structure.md](/Users/youssefjouini/.agents/skills/dataiku/references/plugin-structure.md)

## 5. Dynamic-choice guidance is ambiguous for structured-agent blocks

### Problem

Two different dynamic-choice patterns are described:

- general plugin parameters via `paramsPythonSetup` in [`parameters.md`](/Users/youssefjouini/.agents/skills/dataiku/references/parameters.md)
- block-local `dynamic_choices.py` in [`visual-agent-blocks.md`](/Users/youssefjouini/.agents/skills/dataiku/references/visual-agent-blocks.md)

During this session:

- adding `paramsPythonSetup` caused plugin installation failure
- block-local `dynamic_choices.py` may be the right path for this component type
- support for `MULTISELECT + getChoicesFromPython` on structured-agent blocks still needs confirmation

### Action

Clarify, specifically for structured-agent blocks:

- whether `paramsPythonSetup` is supported
- whether block-local `dynamic_choices.py` is the correct and only supported mechanism
- whether `MULTISELECT` supports dynamic choices in this component type

## 6. `$dku-cli` plugin deployment guidance should be more explicit about install vs update

### Problem

We hit a concrete workflow trap:

- `dku plugin push ... --install` failed once the plugin already existed
- `dku plugin push ... --update` succeeded

The current guidance already describes install and update flows, but it should be more explicit that:

- `--install` is for first install only
- `--update` is for existing plugins
- if install fails on an existing plugin, retry with update

### Action

Strengthen the `$dku-cli` plugin lifecycle section with a prescriptive note and a short failure-recovery snippet.

### Files to review

- [$dku-cli SKILL.md](/Users/youssefjouini/.agents/skills/dku-cli/SKILL.md)
- [commands.md](/Users/youssefjouini/.agents/skills/dku-cli/references/commands.md)

## 7. `$dku-cli` should explicitly mention keychain/sandbox auth caveats

### Problem

Running `dku` inside the sandbox hit:

```text
Can't get password from keychain: (-50, 'Unknown Error')
```

That is a real agentic operating condition when credentials are stored in the macOS keychain.

### Action

Add a short troubleshooting note:

- if `dku` cannot read saved credentials from keychain in a restricted environment, rerun unsandboxed or pass auth via env/flags

### Files to review

- [$dku-cli SKILL.md](/Users/youssefjouini/.agents/skills/dku-cli/SKILL.md)

## 8. `$dku-cli` command-surface assumptions can drift from the installed version

### Problem

Early in the session, the active `dku` binary did not appear to expose the full plugin command set expected by the skill guidance. Later checks showed `create-code-env`, `set-code-env`, `update-code-env`, etc. were present.

The practical issue is that agents should not assume the installed CLI surface matches the repo docs without checking `--help`.

### Action

Add stronger guidance to `$dku-cli`:

- for plugin workflows, inspect `dku plugin --help` on the current machine before assuming subcommands exist
- especially important when multiple `dku` versions may be installed

## 9. `$dataiku` should encourage minimal dependency parsing for demo plugins

### Problem

We temporarily hit:

```text
ModuleNotFoundError: No module named 'yaml'
```

because the plugin runtime did not yet have the expected dependency available.

For this demo plugin, only `name` and `description` from `SKILL.md` frontmatter were needed. A minimal parser would have reduced code-env dependency coupling for the demo path.

### Action

Add a best-practice note:

- for demos and early prototypes, avoid adding parser/runtime dependencies unless they materially simplify the implementation
- when only a few frontmatter fields are required, consider a minimal built-in parser first

### Files to review

- [best-practices.md](/Users/youssefjouini/.agents/skills/dataiku/references/best-practices.md)
- [code-environments.md](/Users/youssefjouini/.agents/skills/dataiku/references/code-environments.md)

## 10. The block references should document message injection semantics for structured-agent blocks

### Problem

For the working runtime contract, message injection is done through:

```python
self.sequence_context.generated_messages.append({"role": "system", "content": ...})
```

not through `context.messages`.

This is operationally important because:

- it affects how pre-chain blocks inject context
- it affects what later blocks and the LLM see
- it changes how agents should reason about “conversation state”

### Action

Document message injection and sequencing explicitly for the structured-agent runtime, using the local working plugin as the example.

## 11. Follow-up technical investigation still needed

These are not yet resolved from the session and should be verified on DSS:

- whether `MULTISELECT + getChoicesFromPython` is supported on `python-structured-agent-blocks`
- whether block-local `dynamic_choices.py` is auto-discovered for structured-agent blocks without any extra descriptor field
- whether there are any additional schema differences between older “visual agent block” docs and DSS 14.4 structured-agent blocks

## Recommended updates

### High priority

- Fix structured-agent block packaging/runtime docs in `$dataiku`
- Add a direct reference to `plugins/agent-semantic-feedback` as the canonical local example
- Clarify parameter-type recommendations in plugin/block guidance
- Clarify dynamic-choice behavior for structured-agent blocks
- Tighten `$dku-cli` guidance around `plugin push --install` vs `--update`

### Medium priority

- Add keychain/sandbox auth troubleshooting to `$dku-cli`
- Add command-surface verification guidance (`--help` first)
- Add minimal-dependency guidance for prototype plugins
