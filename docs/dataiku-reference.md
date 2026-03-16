# Dataiku DSS Quick Reference

Quick reference for common Dataiku operations and concepts.

## GenAI Features Overview

### LLM Mesh

Centralized LLM management layer:
- **Connections**: Configure LLM providers (OpenAI, Anthropic, Azure, AWS Bedrock, Google)
- **Guardrails**: Content filtering, PII detection, cost controls
- **Monitoring**: Usage tracking, latency metrics, cost attribution

### Knowledge Banks

RAG infrastructure:
- Vector storage for document embeddings
- Automatic chunking and indexing
- Semantic search capabilities
- Support for multiple embedding models

### LLM Recipes

| Recipe Type | Use Case |
|-------------|----------|
| **Prompt Engineering** | Text generation, summarization, classification |
| **Embedding** | Generate vector embeddings for semantic search |
| **RAG Query** | Query knowledge banks with context |

### Agents

Autonomous AI capabilities:
- **Agent Tools**: Custom Python functions for agents
- **Built-in Tools**: SQL query, Python execution, web search
- **Orchestration**: Multi-step reasoning with tool use

## Key Concepts

### Projects

Container for all DSS objects:
- Datasets
- Recipes (data transformations)
- Models
- Dashboards
- Code environments

### Flow

Visual representation of data pipeline:
- Datasets as nodes
- Recipes as connections
- Build modes: recursive, non-recursive

### Recipes

Data transformation units:

| Category | Types |
|----------|-------|
| **Visual** | Prepare, Join, Stack, Window |
| **Code** | Python, R, SQL, Spark |
| **ML** | Train, Score, Evaluate |
| **LLM** | Prompt, Embedding, RAG |
| **Plugin** | Custom recipes |

### Scenarios

Automation and orchestration:
- Scheduled runs
- Triggers (dataset change, API call)
- Reporters (email, webhook)
- Metrics and checks

## Common Operations

### Dataset Operations

```python
import dataiku

# Read dataset
dataset = dataiku.Dataset("my_dataset")
df = dataset.get_dataframe()

# Write dataset
output = dataiku.Dataset("output_dataset")
output.write_with_schema(df)

# Get schema
schema = dataset.read_schema()
```

### LLM Operations

```python
import dataiku

# Get LLM handle
client = dataiku.api_client()
project = client.get_project("PROJECT_KEY")
llm = project.get_llm("llm_id")

# Completion
response = llm.complete("Your prompt here")

# With messages
messages = [
    {"role": "system", "content": "You are helpful."},
    {"role": "user", "content": "Hello"}
]
response = llm.chat(messages)
```

### Knowledge Bank Operations

```python
# Query knowledge bank
kb = project.get_knowledge_bank("kb_id")
results = kb.query("search query", top_k=5)

# Get retrieved chunks
for result in results:
    print(result.text, result.score)
```

## Plugin Development

See `~/.claude/docs/dataiku-plugins/` for comprehensive guide.

### Quick Start

```bash
# Create plugin structure
mkdir my-plugin && cd my-plugin

# Essential files
touch plugin.json
mkdir -p python-lib custom-recipes/my-recipe
```

### plugin.json Template

```json
{
  "id": "my-plugin",
  "version": "1.0.0",
  "meta": {
    "label": "My Plugin",
    "description": "Plugin description",
    "author": "Your Name"
  }
}
```

## API Reference

### Python API

```python
import dataiku

# Client
client = dataiku.api_client()

# Project operations
project = client.get_project("PROJECT_KEY")
datasets = project.list_datasets()
recipes = project.list_recipes()

# Dataset operations
dataset = project.get_dataset("dataset_name")
settings = dataset.get_settings()

# Job operations
job = project.start_job(recipe_name)
job.wait_for_completion()
```

### REST API

Base URL: `https://{instance}/public/api/`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/projects` | GET | List projects |
| `/projects/{key}/datasets` | GET | List datasets |
| `/projects/{key}/recipes` | GET | List recipes |
| `/projects/{key}/jobs` | POST | Start job |

## Best Practices

### Performance

- Use partitioning for large datasets
- Leverage Spark for distributed processing
- Use incremental builds where possible

### Security

- Use per-user credentials
- Implement proper access controls
- Audit sensitive operations

### GenAI Specific

- Set token limits and cost controls
- Implement content guardrails
- Monitor for hallucinations
- Use RAG for factual accuracy
