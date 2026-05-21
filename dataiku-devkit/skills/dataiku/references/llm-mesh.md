# Dataiku LLM Mesh & Generative AI

Build enterprise-grade generative AI applications using Dataiku's LLM Mesh framework.

## Overview

The LLM Mesh is Dataiku's comprehensive framework for building, deploying, and managing generative AI applications. It provides a unified interface for working with multiple LLM providers while ensuring security, governance, and cost control.

### Key Components

- **LLM Connections** - Unified interface to multiple LLM providers
- **Agents** - AI applications that use tools to accomplish tasks
- **Tools** - Reusable functions that agents can call
- **Guardrails** - Safety and quality controls for LLM outputs
- **Knowledge Banks** - RAG-enabled knowledge retrieval
- **Prompt Studios** - Prompt engineering and testing
- **Governance** - Auditing, cost tracking, quality monitoring

## LLM Connections

### Accessing LLMs

```python
import dataiku

# Get project client
client = dataiku.api_client()
project = client.get_default_project()

# List available LLMs
llm_list = project.list_llms()
for llm in llm_list:
    print(f"{llm.description} (id: {llm.id})")

# Get specific LLM
llm_id = "openai:my_connection:gpt-4o"
llm = project.get_llm(llm_id)
```

### Basic Completion

```python
# Create completion
completion = llm.new_completion()
completion.with_message("What is machine learning?")

# Get response
response = completion.execute()
print(response.text)
```

### Chat Conversations

```python
# Multi-turn conversation
completion = llm.new_completion()
completion.with_message("What is Python?", role="user")
completion.with_message("Python is a programming language.", role="assistant")
completion.with_message("What are its main features?", role="user")

response = completion.execute()
print(response.text)
```

### LangChain Integration

```python
from langchain_core.messages import HumanMessage, SystemMessage

# Get LangChain chat model
llm_langchain = llm.as_langchain_chat_model()

# Use with LangChain
messages = [
    SystemMessage(content="You are a helpful assistant."),
    HumanMessage(content="Explain quantum computing in simple terms.")
]

response = llm_langchain.invoke(messages)
print(response.content)
```

## Tools

Tools allow LLMs to perform actions and retrieve information. There are two approaches depending on context.

### Plugin Agent Tools (production — BaseAgentTool)

For plugin-packaged tools deployed via DSS, extend `BaseAgentTool`:

```python
from dataiku.llm.agent_tools import BaseAgentTool

TOOL_DESCRIPTION = """Use this tool to calculate the sum of two numbers."""

class CalculateSumTool(BaseAgentTool):
    def get_descriptor(self, tool):
        return {
            "description": TOOL_DESCRIPTION,
            "inputSchema": {
                "type": "object",
                "properties": {
                    "a": {"type": "integer", "description": "First number"},
                    "b": {"type": "integer", "description": "Second number"},
                },
                "required": ["a", "b"],
            },
        }

    def set_config(self, config, plugin_config):
        pass  # Initialize from DSS config

    def invoke(self, input, trace):
        params = input.get("input", {})
        result = params["a"] + params["b"]
        return {"output": f"The sum is {result}"}
```

Each tool lives in `python-agent-tools/{tool-name}/` with `tool.py` + `tool.json`.

### LangChain Tools (prototyping / notebooks)

For quick prototyping in notebooks or code recipes (not plugin-packaged):

```python
from langchain_core.tools import tool

@tool
def calculate_sum(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b

# Bind to LLM
llm_with_tools = llm_langchain.bind_tools([calculate_sum])
```

> **Important**: `@tool` decorator is for LangChain prototyping only. For production plugin tools, always use `BaseAgentTool`.

### Using LangChain Tools with LLM

```python
from langchain_core.messages import HumanMessage

llm_with_tools = llm_langchain.bind_tools(tools)
messages = [HumanMessage("What's 25 + 17?")]
ai_msg = llm_with_tools.invoke(messages)

for tool_call in ai_msg.tool_calls:
    tool_name = tool_call["name"]
    selected_tool = tools_by_name[tool_name]
    tool_result = selected_tool.invoke(tool_call)
    print(f"{tool_name}: {tool_result}")
```

### Tool Choice Control

```python
# Let LLM decide
completion.settings["toolChoice"] = {"type": "auto"}

# Must call at least one tool
completion.settings["toolChoice"] = {"type": "required"}

# Must not call any tool
completion.settings["toolChoice"] = {"type": "none"}

# Must call specific tool
completion.settings["toolChoice"] = {
    "type": "tool_name",
    "name": "calculate_sum"
}
```

## Agents

Agents are LLM-powered applications that use tools to accomplish tasks.

> **Production agents:** For production plugin agents, always use `BaseAgentTool` + DSS's Visual Agent or SVA infrastructure — not LangChain's `AgentExecutor` (deprecated). For agentic tools with internal LangGraph loops, see `references/agent-tool-patterns.md` (the `DKUChatModel` + LangGraph pattern from `dss-plugin-semantic-models-lab`).

### LangGraph Agent Loop (recommended for agentic tools)

```python
from langgraph.graph import StateGraph, END
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage

# Internal tools use @tool decorator (not BaseAgentTool)
@tool
def calculate_sum(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

# Wrap DSS LLM for LangChain/LangGraph compatibility
from dataiku.langchain import DKUChatModel
llm = DKUChatModel(llm_id).bind_tools([calculate_sum])

# Build graph
graph = StateGraph(...)
# ... see agent-tool-patterns.md for full LangGraph pattern
```

### Minimal ReAct Loop (notebooks / prototyping only)

```python
from langchain_core.messages import HumanMessage, ToolMessage

def run_agent(query: str, llm_langchain, tools, max_iterations=5):
    """Minimal tool-calling loop for notebooks. Use LangGraph for production."""
    tools_by_name = {t.name: t for t in tools}
    llm_with_tools = llm_langchain.bind_tools(tools)
    messages = [HumanMessage(content=query)]

    for _ in range(max_iterations):
        ai_msg = llm_with_tools.invoke(messages)
        messages.append(ai_msg)
        if not ai_msg.tool_calls:
            return ai_msg.content
        for call in ai_msg.tool_calls:
            result = tools_by_name[call["name"]].invoke(call)
            messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

    return "Max iterations reached"
```

## Managing Agents via Python API

### Listing and Accessing Agents

```python
import dataiku

client = dataiku.api_client()
project = client.get_default_project()

agents = project.list_agents()
agent = project.get_agent("AGENT_ID")
```

### Reading Agent Configuration

```python
settings = agent.get_settings()
raw = settings.get_raw()

active_vid = raw['activeVersion']
active = next(v for v in raw['versions'] if v['versionId'] == active_vid)

if raw['type'] == 'TOOLS_USING_AGENT':
    prompt = active['toolsUsingAgentSettings']['systemPromptAppend']
    llm_id = active['toolsUsingAgentSettings']['llmId']
    tools = active['toolsUsingAgentSettings']['tools']
elif raw['type'] == 'RAG_LLM':
    prompt = active['ragllmSettings']['contextMessage']
```

### Creating a New Agent Version

Always create a new version when modifying agent settings — never edit in place. The CLI handles deep-copy, next-id selection, and the saved-model activation step in one verb:

```bash
# Just publish a new prompt as v(N+1) and flip active in one call
dku agent set-prompt AGENT_ID --prompt @sys.txt --new-version --activate -P PROJ

# Or do it explicitly: copy then mutate
dku agent create-version AGENT_ID --activate -P PROJ
dku agent list-versions AGENT_ID -P PROJ

# Roll back
dku agent set-active-version AGENT_ID v1 -P PROJ
```

`set-llm` and `add-tool` accept the same `--new-version --activate` flags. Without these flags the CLI mutates the active version in place (legacy default; kept for backwards compatibility, not recommended for prompt iteration).

If you need to do this from Python instead of the CLI (e.g. inside a recipe), the recipe is: deep-copy the active version, set a fresh `versionId`, refresh `versionTag` / `creationTag`, append to `raw['versions']`, `settings.save()`, then `project.get_saved_model(agent_id).set_active_version(new_vid)` — setting `activeVersion` in raw alone does not persist on the server.

## Guardrails

Guardrails intercept LLM completions to enforce safety, compliance, and quality policies. They can block queries (raise an exception) or rewrite content (mutate the `input` dict).

> **Full reference**: See `references/guardrails.md` for `BaseGuardrail` implementation, `guardrail.json` template, and all patterns (content filter, PII detection, LLM judge, token budget).

Each guardrail lives in `python-guardrails/{name}/` with `guardrail.py` + `guardrail.json`.

```python
from dataiku.llm.guardrails import BaseGuardrail

class MyGuardrail(BaseGuardrail):
    def set_config(self, config, plugin_config):
        self.config = config

    def process(self, input, trace):
        with trace.subspan("My Guardrail") as span:
            # Check query (before LLM)
            messages = input.get("completionQuery", {}).get("messages", [])
            if messages:
                text = messages[-1].get("content", "")
                if "blocked" in text.lower():
                    raise Exception("Query blocked.")  # Block

            # Check response (after LLM)
            resp = input.get("completionResponse", {})
            if resp.get("text"):
                input["completionResponse"]["text"] = resp["text"]  # Rewrite

            span.attributes["checked"] = True
        return input  # Always return input
```

## Knowledge Banks & RAG

### Creating Knowledge Bank

```python
# Get knowledge bank
kb_list = project.list_knowledge_banks()
kb = project.get_knowledge_bank('my_kb_id')

# Get core handle
kb_core = kb.as_core_knowledge_bank()
```

### Adding Documents

```python
kb_core.add_documents([
    {
        'id': 'doc1',
        'content': 'Document content',
        'metadata': {'source': 'manual', 'category': 'product'}
    }
])
```

### Embedding Models

| Provider | Model | Dimensions |
|----------|-------|------------|
| OpenAI | text-embedding-3-large | 3072 |
| OpenAI | text-embedding-3-small | 1536 |
| Cohere | embed-english-v3.0 | 1024 |
| AWS Bedrock | Titan Embeddings | 1536 |
| Custom | Any sentence-transformers | Varies |

### Chunking Strategies

| Strategy | Best For |
|----------|----------|
| **Fixed Size** | Uniform documents |
| **Sentence** | Natural text |
| **Paragraph** | Structured documents |
| **Recursive** | Mixed content |
| **Semantic** | Topic-based retrieval |

**Chunk tuning:**
- **Size**: 256–512 tokens for most use cases
- **Overlap**: 10–20% for context continuity
- **Metadata**: Include source, date, category for filtering
- **Hybrid search**: Combine semantic + keyword for precision

### RAG Query Pattern

```python
def rag_query(question: str, kb, llm):
    """Query with RAG pattern."""

    # Search knowledge bank
    core_kb = kb.as_core_knowledge_bank()
    search_results = core_kb.search_vectors(
        query=question,
        k=5
    )

    # Extract context
    context = "\n\n".join([
        doc['content'] for doc in search_results
    ])

    # Build prompt with context
    prompt = f"""Use this context to answer:

{context}

Question: {question}

Answer:"""

    # Get response
    completion = llm.new_completion()
    completion.with_message(prompt)
    response = completion.execute()

    return response.text
```

## LLM Recipes (Visual)

Visual recipes for LLM-powered data processing — no code required.

### Prompt Engineering Recipe

Apply a prompt template to every row in a dataset.

| Parameter | Description |
|-----------|-------------|
| System Prompt | Define model behavior |
| User Prompt | Template with `{{column_name}}` references |
| Temperature | 0 (deterministic) to 1 (creative) |
| Max Tokens | Output length limit |
| Stop Sequences | Early termination triggers |

Column reference syntax: `Summarize this text: {{text_column}}`

### Embedding Recipe

Converts a text column to a vector embedding column (array of floats). Use to prepare data for semantic search, clustering, or similarity computation.

### RAG Query Recipe

Queries a Knowledge Bank and injects retrieved context into a prompt template. Parameters: knowledge bank selection, top-K retrieval count, similarity threshold, prompt template with `{{context}}` placeholder.

---

## Cost Control

### Rate Limiting

```python
completion = llm.new_completion()
completion.settings["rateLimit"] = {
    "requestsPerMinute": 60,
    "tokensPerMinute": 100000
}
```

### Token Budgets

```python
completion.settings["maxTokens"] = 1000

response = completion.execute()
usage = response.get_usage()
print(f"Prompt tokens: {usage.prompt_tokens}")
print(f"Completion tokens: {usage.completion_tokens}")
```

## Best Practices

### Agent Design
- **Clear tool descriptions** - Help LLM understand tool usage
- **Error handling** - Graceful failure recovery
- **Iteration limits** - Prevent infinite loops
- **Memory management** - Clear old context appropriately
- **Tool validation** - Validate inputs and outputs

### Guardrail Design
- **Layered approach** - Multiple complementary guardrails
- **Performance** - Keep guardrails fast
- **Logging** - Track when guardrails trigger
- **Testing** - Test with adversarial inputs

### RAG Optimization
- **Chunk size** - Balance context and relevance
- **Retrieval quality** - Test search results
- **Context formatting** - Clear source attribution
- **Fallback handling** - Handle no-results cases
- **Update strategy** - Keep knowledge current

### Cost Management
- **Model selection** - Right model for task
- **Prompt optimization** - Minimize token usage
- **Caching** - Cache repeated queries
- **Rate limiting** - Prevent runaway costs
- **Monitoring** - Track usage and costs

---

## DSS 14 Additions

### OpenAI-Compatible API Endpoint

DSS exposes an OpenAI-compatible endpoint for each project. External tools (Cursor, Continue, custom apps) can use DSS as an OpenAI-compatible backend:

```
http://<DSS_HOST>/public/api/projects/<PROJECT_KEY>/llms/openai/v1/
```

This enables any tool that supports the OpenAI API format to route through DSS with its governance, guardrails, and cost controls applied.

### Image Generation

```python
# Generate images via LLM Mesh (DSS 14+)
gen = llm.new_images_generation()
gen.with_prompt("A diagram showing data flow architecture")
result = gen.execute()
```

### Reranking for RAG

```python
# Rerank search results for better RAG quality (Cohere, others)
reranker = llm.new_reranking()
reranker.with_query("How does authentication work?")
reranker.with_documents(search_results)
result = reranker.execute()
```

### Additional DSS 14 LLM Features

- **Automatic throttling** — DSS auto-manages rate limits per LLM connection
- **Streaming for Anthropic** — Streaming completions now supported for Anthropic models
- **Multimodal tool outputs** — Agent tools can return images, not just text
- **Image inputs** — Completion queries can include images
- **Milvus/Zilliz vector stores** — New vector store options for Knowledge Banks
- **Vector similarity metric selection** — Choose cosine, dot product, or Euclidean
- **A2A Server** — DSS can be exposed as an Agent-to-Agent server (JSON-RPC, HTTP-SSE)

### New LLM Connection Types (DSS 14)

Full provider list: OpenAI, Azure OpenAI, Azure AI Foundry, Anthropic, AWS Bedrock, AWS SageMaker, Cohere, Databricks, Google Vertex, Mistral AI, NVIDIA NIM, Snowflake Cortex, Stability AI, HuggingFace (local).
