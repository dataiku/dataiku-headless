# Code Agent (`PYTHON_AGENT`)

A code agent is a custom Python class that subclasses `BaseLLM` from `dataiku.llm.python`. Dataiku invokes the class directly; the implementation owns all LLM calls, tool dispatch, memory management, and response shaping.

Use a code agent only when simple and structured agents cannot meet the requirement, such as for custom streaming, multimodal processing, external SDK integration, or bespoke control flow.

## Execution Contract

Implement exactly one of these methods:

- `process`
- `aprocess`
- `process_stream`
- `aprocess_stream`

Each receives the conversation query, completion settings, and a trace builder. The streaming variants yield response chunks; the non-streaming variants return a response object.

## Interpreting Configuration

- `code` contains the full Python implementation.
- `code_env_name` identifies the code environment used by the agent.
- `supports_image_inputs` enables image input in the chat interface.

The class can declare dependencies on Dataiku objects, such as datasets, saved models, and knowledge banks, so the Flow represents those dependencies.

## Design Guidance

Keep logic observable through the provided trace builder. Treat input parsing, error handling, external-service behavior, and conversation memory as explicit implementation responsibilities; none are provided by a built-in agent loop.
