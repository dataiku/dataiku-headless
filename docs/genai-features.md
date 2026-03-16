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
    │
    ▼
┌─────────────────┐
│   LLM (Brain)   │
└────────┬────────┘
         │ Reasoning
         ▼
┌─────────────────┐
│  Tool Selection │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐ ┌───────┐
│Tool 1 │ │Tool 2 │
└───────┘ └───────┘
    │         │
    └────┬────┘
         ▼
┌─────────────────┐
│  Final Response │
└─────────────────┘
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

Create via plugins (`python-llm-tools/`):

```python
def run(payload, config, plugin_config, inputs):
    """
    Execute the tool.

    Args:
        payload: Tool input from LLM
        config: Tool configuration
        plugin_config: Plugin-level config
        inputs: Input datasets

    Returns:
        Tool output for LLM
    """
    query = payload.get("query")
    # Process and return result
    return {"result": processed_result}
```

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
# Backend (Flask)
from dataiku import api_client

client = api_client()
project = client.get_project("PROJECT_KEY")
llm = project.get_llm("my-llm")

@app.route('/api/generate', methods=['POST'])
def generate():
    prompt = request.json['prompt']
    response = llm.complete(prompt)
    return jsonify({'response': response})
```

---

## Common Use Cases by Industry

### Financial Services
| Use Case | Features Used |
|----------|---------------|
| Document summarization | Prompt recipe |
| Risk report generation | RAG + Prompt |
| Regulatory Q&A | Knowledge Bank + Agent |
| Contract analysis | Extraction recipe |

### Healthcare / Life Sciences
| Use Case | Features Used |
|----------|---------------|
| Clinical trial analysis | RAG + Summarization |
| Medical literature review | Knowledge Bank |
| Patient communication | Prompt + Guardrails |
| Adverse event detection | Classification recipe |

### Retail / CPG
| Use Case | Features Used |
|----------|---------------|
| Product description generation | Prompt recipe |
| Customer review analysis | Classification + Extraction |
| Inventory Q&A | SQL Agent |
| Marketing content | Prompt + RAG |

### Manufacturing
| Use Case | Features Used |
|----------|---------------|
| Maintenance documentation Q&A | Knowledge Bank |
| Quality report summarization | Prompt recipe |
| Process optimization insights | Agent + SQL |
| Supplier communication | Prompt + Guardrails |

---

## Demo Scenarios

### Quick Wins (< 1 week to value)
1. **Document Summarization** - Reduce manual reading time
2. **Text Classification** - Automate categorization
3. **FAQ Bot** - Answer common questions

### Strategic Projects (1-3 months)
1. **Enterprise Knowledge Assistant** - Company-wide RAG
2. **Automated Report Generation** - Scheduled insights
3. **Customer Service Agent** - Multi-tool autonomous agent

### Differentiators vs. Alternatives

| Capability | Dataiku Advantage |
|------------|-------------------|
| Governance | Enterprise-grade LLM Mesh |
| Integration | Unified with data platform |
| Scalability | Production-ready pipelines |
| Flexibility | Any LLM, any deployment |
| Collaboration | Visual + code, all personas |
