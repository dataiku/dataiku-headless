# Dataiku GenAI Features Catalog

Comprehensive reference for GenAI capabilities in Dataiku DSS.

---

## LLM Mesh

Centralized LLM governance and management layer.

### Supported Providers

| Provider | Models | Connection Type |
|----------|--------|-----------------|
| **OpenAI** | GPT-4o, GPT-4 Turbo, GPT-3.5 | API Key |
| **Anthropic** | Claude 3 Opus/Sonnet/Haiku | API Key |
| **Azure OpenAI** | GPT-4, GPT-3.5 | Azure credentials |
| **AWS Bedrock** | Claude, Titan, Llama | IAM/Access Keys |
| **Google Vertex AI** | Gemini Pro, PaLM | Service Account |
| **Cohere** | Command, Embed | API Key |
| **Custom/Local** | Any OpenAI-compatible | Base URL + Key |

### Key Features

**Governance**
- Centralized credential management
- Per-project LLM access controls
- Usage quotas and limits
- Audit logging

**Cost Controls**
- Token budgets per user/project
- Rate limiting
- Cost attribution and tracking

**Guardrails**
- Content filtering (toxicity, bias)
- PII detection and redaction
- Custom blocklists
- Output validation

---

## Knowledge Banks (RAG)

Enterprise RAG infrastructure for grounded AI responses.

### Components

| Component | Purpose |
|-----------|---------|
| **Document Sources** | Ingest from datasets, folders, web |
| **Chunking** | Split documents into retrievable segments |
| **Embedding** | Convert chunks to vector representations |
| **Vector Store** | Store and index embeddings |
| **Retrieval** | Semantic search for relevant context |

### Embedding Models

| Provider | Model | Dimensions |
|----------|-------|------------|
| OpenAI | text-embedding-3-large | 3072 |
| OpenAI | text-embedding-3-small | 1536 |
| Cohere | embed-english-v3.0 | 1024 |
| AWS | Titan Embeddings | 1536 |
| Custom | Any sentence-transformers | Varies |

### Chunking Strategies

| Strategy | Best For |
|----------|----------|
| **Fixed Size** | Uniform documents |
| **Sentence** | Natural text |
| **Paragraph** | Structured documents |
| **Recursive** | Mixed content |
| **Semantic** | Topic-based retrieval |

### Best Practices

- **Chunk size**: 256-512 tokens for most use cases
- **Overlap**: 10-20% for context continuity
- **Metadata**: Include source, date, category for filtering
- **Hybrid search**: Combine semantic + keyword for precision

---

## LLM Recipes

Visual recipes for LLM-powered data processing.

### Prompt Engineering Recipe

**Use Cases**:
- Text generation
- Summarization
- Classification
- Extraction
- Translation

**Key Parameters**:
| Parameter | Description |
|-----------|-------------|
| System Prompt | Define model behavior |
| User Prompt | Template with column references |
| Temperature | 0 (deterministic) to 1 (creative) |
| Max Tokens | Output length limit |
| Stop Sequences | Early termination triggers |

**Column References**:
```
Summarize this text: {{text_column}}
Classify the sentiment: {{review}}
```

### Embedding Recipe

**Use Cases**:
- Prepare data for vector search
- Similarity computation
- Clustering preparation

**Output**: Adds embedding column (array of floats)

### RAG Query Recipe

**Use Cases**:
- Question answering over documents
- Grounded content generation
- Research assistance

**Parameters**:
- Knowledge Bank selection
- Top-K retrieval count
- Similarity threshold
- Prompt template with retrieved context

---

## Agents

Autonomous AI with tool use capabilities.

### Architecture

```
User Query
    |
    v
+-----------------+
|   LLM (Brain)   |
+--------+--------+
         | Reasoning
         v
+-----------------+
|  Tool Selection |
+--------+--------+
         |
    +----+----+
    v         v
+-------+ +-------+
|Tool 1 | |Tool 2 |
+-------+ +-------+
    |         |
    +----+----+
         v
+-----------------+
|  Final Response |
+-----------------+
```

### Built-in Tools

| Tool | Description |
|------|-------------|
| **SQL Query** | Query datasets with natural language |
| **Python** | Execute Python code |
| **Retrieval** | Search knowledge banks |
| **Web Search** | Search the internet |
| **Calculator** | Mathematical operations |

### Custom Agent Tools

Create via plugins (`python-agent-tools/`):

```python
from dataiku.llm.agent_tools import BaseAgentTool

class MyTool(BaseAgentTool):
    def set_config(self, config, plugin_config):
        self.config = config

    def get_descriptor(self, tool_config, trace):
        return {
            "description": "What this tool does",
            "inputSchema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }

    def invoke(self, input, trace):
        args = input.get("input", {})  # NOT root of input dict
        query = args.get("query")
        # Process and return result
        return {"output": str(result)}
```

See `llm-tools.md` for detailed patterns, gotchas, and testing guidance.

### Agent Configuration

| Setting | Recommendation |
|---------|----------------|
| Max iterations | 5-10 for most tasks |
| Temperature | 0-0.3 for tool use |
| Model | GPT-4 or Claude 3 for complex reasoning |
| Timeout | 60-120s per iteration |

---

## Webapp Integration

Embed GenAI in interactive applications.

### Chat Interface

Built-in chat webapp for conversational AI:
- Custom system prompts
- Knowledge bank integration
- Conversation history
- User feedback collection

### Custom Webapps

Integrate LLM capabilities in custom webapps:

```python
# Plugin webapp backend (DSS provides `app` — do NOT create your own)
from dataiku import api_client
from flask import request, jsonify

client = api_client()
project = client.get_project(dataiku.default_project_key())
llm = project.get_llm("my-llm")

@app.route('/generate', methods=['POST'])
def generate():
    prompt = request.json['prompt']
    completion = llm.new_completion()
    completion.with_message(prompt)
    response = completion.execute()
    return jsonify({'response': response.text})
```

See `webapps.md` and `webapp-pitfalls.md` for full webapp patterns.
