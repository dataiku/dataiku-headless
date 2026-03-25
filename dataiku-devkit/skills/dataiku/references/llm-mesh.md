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

### Basic Agent Pattern

```python
from langchain.agents import create_react_agent, AgentExecutor
from langchain import hub

# Get ReAct prompt template
prompt = hub.pull("hwchase17/react")

# Create agent
agent = create_react_agent(
    llm=llm_langchain,
    tools=tools,
    prompt=prompt
)

# Create executor
agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,
    max_iterations=10
)

# Run agent
result = agent_executor.invoke({
    "input": "Calculate 25 + 17"
})
print(result["output"])
```

### Custom Agent Loop

```python
def run_agent(query: str, llm, tools, max_iterations=5):
    """Custom agent execution loop."""
    tools_by_name = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(tools)

    messages = [HumanMessage(content=query)]

    for iteration in range(max_iterations):
        # Get LLM response
        ai_msg = llm_with_tools.invoke(messages)
        messages.append(ai_msg)

        # Check if done
        if not ai_msg.tool_calls:
            return ai_msg.content

        # Execute tool calls
        for tool_call in ai_msg.tool_calls:
            tool_name = tool_call["name"]
            tool = tools_by_name[tool_name]
            result = tool.invoke(tool_call)
            messages.append(ToolMessage(
                content=str(result),
                tool_call_id=tool_call["id"]
            ))

    return "Max iterations reached"
```

### Agent with Memory

```python
from langchain.memory import ConversationBufferMemory

# Create memory
memory = ConversationBufferMemory(
    memory_key="chat_history",
    return_messages=True
)

# Create agent with memory
agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    memory=memory,
    verbose=True
)

# Multi-turn conversation
agent_executor.invoke({"input": "My name is Alice"})
agent_executor.invoke({"input": "What's my name?"})
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

Always create a new version when modifying agent settings — never edit in place.

```python
import copy, time

settings = agent.get_settings()
raw = settings.get_raw()

# Determine next version ID
versions = raw.get('versions', [])
version_nums = [int(v['versionId'].replace('v', '')) for v in versions if v['versionId'].startswith('v')]
new_vid = f"v{max(version_nums) + 1 if version_nums else 1}"

# Deep-copy active version as base
active_vid = raw['activeVersion']
active_version = next(v for v in versions if v['versionId'] == active_vid)
new_version = copy.deepcopy(active_version)
new_version['versionId'] = new_vid
now_ms = int(time.time() * 1000)
new_version['versionTag'] = {'versionNumber': 0, 'lastModifiedBy': {'login': 'api'}, 'lastModifiedOn': now_ms}
new_version['creationTag'] = {'versionNumber': 0, 'lastModifiedBy': {'login': 'api'}, 'lastModifiedOn': now_ms}

# Apply changes
if raw['type'] == 'TOOLS_USING_AGENT':
    new_version['toolsUsingAgentSettings']['systemPromptAppend'] = "New prompt here"
elif raw['type'] == 'RAG_LLM':
    new_version['ragllmSettings']['contextMessage'] = "New context message"

raw['versions'].append(new_version)
settings.save()
```

### Activating a Version

Agents are saved models — use the saved model API to change the active version (setting `activeVersion` in raw does not work).

```python
sm = project.get_saved_model("AGENT_ID")
sm.set_active_version(new_vid)

# Verify
print(sm.get_active_version()['id'])
```

## Guardrails

Guardrails provide safety and quality controls for LLM applications.

### Custom Guardrail Component

```
python-guardrails/
└── my-guardrail/
    ├── guardrail.json
    └── guardrail.py
```

### Plugin Guardrail Implementation (BaseGuardrail)

For plugin-packaged guardrails, extend `BaseGuardrail`. This is the current API (DSS 14.x):

```python
import logging
from dataiku.llm.guardrails import BaseGuardrail

class ContentFilterGuardrail(BaseGuardrail):
    """Content filtering guardrail using BaseGuardrail pattern."""

    def set_config(self, config, plugin_config):
        """Initialize from DSS plugin configuration."""
        self.blocked_terms = config.get("blockedTerms", [])
        self.check_queries = config.get("checkQueries", True)
        self.check_responses = config.get("checkResponses", True)

    def process(self, input, trace):
        """Process input — check queries and/or responses for violations."""
        with trace.subspan("Content Filter Guardrail") as subspan:
            # Check queries
            if self.check_queries and "completionQuery" in input:
                messages = input.get("completionQuery", {}).get("messages", [])
                if messages:
                    last_msg = messages[-1]
                    text = last_msg.get("content", "")
                    for term in self.blocked_terms:
                        if term.lower() in text.lower():
                            logging.warning("[Content Filter] Blocked term detected in query")
                            raise Exception("Query blocked: prohibited content detected.")

            # Check responses
            if self.check_responses and "completionResponse" in input:
                text = input.get("completionResponse", {}).get("text", "")
                for term in self.blocked_terms:
                    if term.lower() in text.lower():
                        logging.warning("[Content Filter] Blocked term detected in response")
                        input["completionResponse"]["text"] = "Response blocked: prohibited content."

        return input
```

Each guardrail lives in `python-guardrails/{name}/` with `guardrail.py` + `guardrail.json`.

### Guardrail Patterns

**PII Detection:**
```python
def process(self, input, trace):
    import re
    with trace.subspan("PII Detection") as subspan:
        if "completionQuery" in input:
            messages = input["completionQuery"].get("messages", [])
            if messages:
                text = messages[-1].get("content", "")
                if re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text):
                    raise Exception("Query contains PII. Please remove email addresses.")
    return input
```

**LLM Judge (delegate to another LLM):**
```python
def process(self, input, trace):
    with trace.subspan("LLM Judge") as subspan:
        if "completionQuery" in input:
            messages = input["completionQuery"].get("messages", [])
            if messages:
                text = messages[-1].get("content", "")
                completion = self.llm_judge.new_completion()
                completion.with_message(self.system_prompt, role="system")
                completion.with_message(f"Check this: {text}\nViolation? yes/no", role="user")
                resp = completion.execute()
                if subspan and hasattr(resp, "trace"):
                    subspan.append_trace(resp.trace)
                if "yes" in resp.text.strip().lower():
                    raise Exception(self.block_message)
    return input
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
