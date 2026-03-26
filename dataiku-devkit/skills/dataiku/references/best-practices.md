# Best Practices & Design Patterns

> Production-grade patterns and guidelines for building robust Dataiku plugins.

---

## Architecture Principles

### 1. Separation of Concerns

```
my-plugin/
├── python-lib/              # Core business logic
│   └── my_plugin/
│       ├── core/            # Domain logic (no Dataiku imports)
│       │   ├── models.py    # Data models
│       │   ├── processors.py
│       │   └── validators.py
│       ├── adapters/        # Dataiku integration
│       │   ├── datasets.py  # Dataset I/O
│       │   └── llm.py       # LLM wrapper
│       └── utils.py         # Shared utilities
├── custom-recipes/          # Thin wrappers calling core logic
│   └── my-recipe/
│       ├── recipe.json
│       └── recipe.py        # Minimal: config -> core -> output
└── python-agent-tools/      # Tool interfaces
    └── my-tool/
        ├── tool.json
        └── tool.py          # Minimal: invoke -> core -> response
```

### 2. Configuration Management

```python
# python-lib/my_plugin/config.py
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ProcessingConfig:
    """Strongly-typed configuration."""
    llm_id: str
    batch_size: int = 10
    max_concurrent: int = 4
    temperature: float = 0.7
    categories: List[str] = field(default_factory=list)
    custom_prompt: Optional[str] = None

    @classmethod
    def from_recipe_config(cls, config: dict) -> "ProcessingConfig":
        """Create from Dataiku recipe config dict."""
        return cls(
            llm_id=config.get("llm_id"),
            batch_size=config.get("batch_size", 10),
            max_concurrent=config.get("max_concurrent", 4),
            temperature=config.get("temperature", 0.7),
            categories=config.get("categories", []),
            custom_prompt=config.get("custom_prompt"),
        )

    def validate(self) -> None:
        """Validate configuration."""
        if not self.llm_id:
            raise ValueError("llm_id is required")
        if self.batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
```

### 3. Thread-Safe Config with ContextVar (Advanced)

For plugins that serve both webapp and agent tool contexts, use `ContextVar` for thread-safe config overrides:

```python
# python-lib/my_plugin/config.py
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import Any, Iterator, Optional

@dataclass
class AppConfig:
    dss_project_key: str
    llm_id: Optional[str] = None
    max_rows_per_query: int = 1000
    agent_recursion_limit: int = 100
    sources_records_limit: int = 50

# Global instance + thread-safe override
_config: Optional[AppConfig] = None
_config_override: ContextVar[Optional[AppConfig]] = ContextVar("app_config_override", default=None)

def load_webapp_config() -> AppConfig:
    """Load from DSS webapp context."""
    global _config
    from dataiku.customwebapp import get_webapp_config
    cfg = get_webapp_config()
    _config = AppConfig(
        dss_project_key=dataiku.api_client().get_default_project().project_key,
        llm_id=cfg.get("llm_id"),
        max_rows_per_query=int(cfg.get("max_rows_per_query", 1000)),
    )
    return _config

def load_tool_config(tool_config: dict) -> AppConfig:
    """Load from agent tool set_config()."""
    global _config
    _config = AppConfig(
        dss_project_key=tool_config.get("project_key") or _resolve_project_key(),
        llm_id=tool_config.get("llm_id"),
        max_rows_per_query=int(tool_config.get("max_rows_per_query", 1000)),
    )
    return _config

def load_local_config() -> AppConfig:
    """Load from .env for local development."""
    global _config
    from dotenv import load_dotenv
    load_dotenv()
    _config = AppConfig(
        dss_project_key=os.getenv("DKU_CURRENT_PROJECT_KEY"),
        llm_id=os.getenv("LLM_ID"),
    )
    return _config

def get_app_config() -> AppConfig:
    """Get config — checks ContextVar override first, then global."""
    override = _config_override.get()
    if override is not None:
        return override
    if _config is None:
        raise RuntimeError("AppConfig not initialized. Call load_*_config() first.")
    return _config

@contextmanager
def override_app_config(**overrides: Any) -> Iterator[AppConfig]:
    """Temporarily override config for current context (thread-safe)."""
    if _config is None:
        raise RuntimeError("AppConfig not initialized.")
    merged = replace(_config, **overrides)
    token = _config_override.set(merged)
    try:
        yield merged
    finally:
        _config_override.reset(token)
```

**Why ContextVar?** Without it, a webapp request and an agent tool invocation could stomp on each other's config. `ContextVar` provides per-coroutine/per-thread isolation without explicit thread-local storage.

### 4. Service Factory Pattern

Wrap DSS API quirks behind a service layer. Inject the client for testability:

```python
# python-lib/my_plugin/services/factory.py
from my_plugin.services.client import LocalClient
from my_plugin.services.service import MyService

def get_service(client: LocalClient = None) -> MyService:
    if client is None:
        client = LocalClient()
    return MyService(client=client)

# python-lib/my_plugin/services/client.py
class LocalClient:
    """Wraps dataikuapi, normalizes quirks."""
    def __init__(self, project_key=None):
        import dataiku
        self._client = dataiku.api_client()
        if project_key:
            self._project = self._client.get_project(project_key)
        else:
            self._project = self._client.get_default_project()

    def list_models(self):
        # Normalize DSS camelCase → snake_case, handle API quirks
        raw = self._project._perform_json("GET", "/semantic-models/")
        return [Model.from_dict(m) for m in raw]

# python-lib/my_plugin/services/service.py
class MyService:
    """Business logic — zero DSS imports."""
    def __init__(self, client):
        self.client = client

    def get_active_version(self, model_id):
        model = self.client.get_model(model_id)
        return next(v for v in model.versions if v.id == model.active_version_id)
```

**Benefits:** Core service is testable without DSS. Client abstracts API changes. Factory makes DI explicit.

---

## Error Handling Patterns

### Graceful Degradation

```python
def process_with_fallback(items: List[Dict], primary_llm, fallback_llm) -> List[Dict]:
    """Process with automatic fallback on failure."""
    results = []

    for item in items:
        try:
            result = process_item(item, primary_llm)
        except Exception as primary_error:
            logger.warning(f"Primary LLM failed: {primary_error}, trying fallback")
            try:
                result = process_item(item, fallback_llm)
            except Exception as fallback_error:
                logger.error(f"Fallback also failed: {fallback_error}")
                result = build_error_result(item, str(fallback_error))

        results.append(result)

    return results


def build_error_result(item: Dict, error: str) -> Dict:
    """Create standardized error result matching output schema."""
    return {
        **item,
        "result": None,
        "success": False,
        "error": error,
        "processed_at": datetime.now().isoformat()
    }
```

### Retry with Exponential Backoff

```python
import time
from functools import wraps


def retry_with_backoff(max_retries: int = 3, base_delay: float = 1.0):
    """Decorator for retry with exponential backoff."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            f"Attempt {attempt + 1} failed: {e}. "
                            f"Retrying in {delay}s..."
                        )
                        time.sleep(delay)

            raise last_error

        return wrapper
    return decorator


@retry_with_backoff(max_retries=3, base_delay=2.0)
def call_external_api(endpoint: str, payload: dict) -> dict:
    """Call external API with automatic retry."""
    response = requests.post(endpoint, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()
```

### Comprehensive Error Context

```python
class PluginError(Exception):
    """Base exception with rich context."""

    def __init__(self, message: str, context: dict = None, cause: Exception = None):
        super().__init__(message)
        self.context = context or {}
        self.cause = cause

    def __str__(self):
        parts = [super().__str__()]
        if self.context:
            parts.append(f"Context: {self.context}")
        if self.cause:
            parts.append(f"Caused by: {self.cause}")
        return " | ".join(parts)


class ProcessingError(PluginError):
    """Error during data processing."""
    pass


class LLMError(PluginError):
    """Error from LLM operations."""
    pass


# Usage
try:
    result = process_item(item)
except Exception as e:
    raise ProcessingError(
        "Failed to process item",
        context={"item_id": item.get("id"), "stage": "llm_call"},
        cause=e
    )
```

---

## Performance Patterns

### Parallel Processing with Thread Pool

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, TypeVar
import threading

T = TypeVar("T")
R = TypeVar("R")


class ThreadLocalLLMCache:
    """Thread-local cache for LLM instances."""

    def __init__(self):
        self._local = threading.local()

    def get_llm(self, project, llm_id: str):
        cache_key = f"llm_{llm_id}"
        llm = getattr(self._local, cache_key, None)
        if llm is None:
            llm = project.get_llm(llm_id)
            setattr(self._local, cache_key, llm)
        return llm


def parallel_process(
    items: List[T],
    process_fn: Callable[[T], R],
    max_workers: int = 4,
    progress_callback: Callable[[int, int], None] = None
) -> List[R]:
    """Process items in parallel with progress tracking."""
    results = []
    total = len(items)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_item = {
            executor.submit(process_fn, item): i
            for i, item in enumerate(items)
        }

        completed = 0
        for future in as_completed(future_to_item):
            idx = future_to_item[future]
            try:
                result = future.result()
                results.append((idx, result))
            except Exception as e:
                logger.error(f"Item {idx} failed: {e}")
                results.append((idx, build_error_result(items[idx], str(e))))

            completed += 1
            if progress_callback:
                progress_callback(completed, total)

    # Sort by original index and return just results
    results.sort(key=lambda x: x[0])
    return [r[1] for r in results]
```

### Streaming Large Datasets

Set the output schema from the first chunk **before** opening the writer, then use a single persistent writer for all chunks. Never mix `write_with_schema()` (which truncates the dataset) with a separate `get_writer()` call.

```python
def process_large_dataset(
    input_ds: dataiku.Dataset,
    output_ds: dataiku.Dataset,
    process_fn: Callable,
    chunk_size: int = 10000
) -> dict:
    """Process large dataset in chunks using a single writer."""
    stats = {"processed": 0, "errors": 0}
    chunks = input_ds.iter_dataframes(chunksize=chunk_size)

    # Process first chunk to establish output schema before opening writer
    first = next(chunks, None)
    if first is None:
        return stats
    processed_first = process_fn(first)
    output_ds.write_schema_from_dataframe(processed_first)

    with output_ds.get_writer() as writer:
        writer.write_dataframe(processed_first)
        stats["processed"] += len(first)

        for chunk in chunks:
            processed = process_fn(chunk)
            writer.write_dataframe(processed)
            stats["processed"] += len(chunk)
            logger.info(f"Processed {stats['processed']} rows")

    return stats
```

### Lazy Loading

```python
# python-lib/my_plugin/adapters/lazy.py
"""Lazy loading for expensive imports and connections."""


class LazyLoader:
    """Lazy-load expensive resources on first access."""

    def __init__(self):
        self._dataiku = None
        self._client = None
        self._project = None

    @property
    def dataiku(self):
        if self._dataiku is None:
            import dataiku
            self._dataiku = dataiku
        return self._dataiku

    @property
    def client(self):
        if self._client is None:
            self._client = self.dataiku.api_client()
        return self._client

    @property
    def project(self):
        if self._project is None:
            self._project = self.client.get_default_project()
        return self._project


# Global lazy loader instance
lazy = LazyLoader()


# Usage in backend code
def get_llm(llm_id: str):
    return lazy.project.get_llm(llm_id)
```

---

## Production Logging Patterns

### Request Context Injection

Inject request metadata (request_id, user, method, path) into every log record. Works for both Flask webapp requests and agent tool invocations:

```python
# python-lib/my_plugin/logging_utils.py
import contextvars
import logging
import time
import uuid
from contextlib import contextmanager

try:
    from flask import g, has_request_context, request
except Exception:
    g = None
    request = None
    def has_request_context(): return False

_LOG_CONTEXT: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "log_context", default=None
)

class RequestContextFilter(logging.Filter):
    """Inject request context into every log record."""
    def filter(self, record):
        request_id = user = method = path = "-"

        if has_request_context():
            # Flask webapp context
            request_id = getattr(g, "request_id", "-")
            user = getattr(g, "authIdentifier", "-")
            method = request.method if request else "-"
            path = request.path if request else "-"
        else:
            # Agent tool / background context
            ctx = _LOG_CONTEXT.get()
            if ctx:
                request_id = ctx.get("request_id", "-")
                user = ctx.get("user", "-")

        record.request_id = request_id
        record.user = user
        record.method = method
        record.path = path
        return True

@contextmanager
def log_context(*, request_id=None, user=None, method=None, path=None):
    """Attach context to logs outside Flask scope (for agent tools)."""
    current = _LOG_CONTEXT.get() or {}
    merged = {**current}
    if request_id: merged["request_id"] = request_id
    if user: merged["user"] = user
    if method: merged["method"] = method
    if path: merged["path"] = path

    token = _LOG_CONTEXT.set(merged)
    try:
        yield
    finally:
        _LOG_CONTEXT.reset(token)
```

Usage in agent tools:
```python
def invoke(self, input, trace):
    with log_context(request_id=str(uuid.uuid4()), user=resolve_tool_user(),
                     method="TOOL", path="/agent-tools/my-tool"):
        logger.info("Tool invoked with question: %s", question[:100])
        # All logs within this block include request_id, user, etc.
```

### Sensitive Data Redaction

Prevent credentials from leaking into DSS logs:

```python
SENSITIVE_LOG_KEYS = {"authorization", "password", "token", "access_token", "api_key", "secret"}

def summarize_for_logging(value, *, max_chars=1000, max_items=25, max_depth=4):
    """Size-limited, redacted structure for safe logging."""
    if max_depth <= 0: return "<max-depth>"
    if value is None or isinstance(value, (bool, int, float)): return value
    if isinstance(value, str):
        return value[:max_chars] + f"... [{len(value)-max_chars} truncated]" if len(value) > max_chars else value
    if isinstance(value, dict):
        out = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= max_items:
                out["__truncated__"] = len(value) - max_items
                break
            if k.lower() in SENSITIVE_LOG_KEYS:
                out[k] = "[redacted]"
            else:
                out[k] = summarize_for_logging(v, max_chars=max_chars, max_depth=max_depth-1)
        return out
    if isinstance(value, (list, tuple)):
        return [summarize_for_logging(v, max_depth=max_depth-1) for v in value[:max_items]]
    return str(value)[:max_chars]
```

### Request Timing Hooks

Add before/after request hooks for automatic timing and audit logging:

```python
def install_request_logging_hooks(app):
    if getattr(app, "_request_logging_installed", False):
        return

    @app.before_request
    def _before():
        g.request_id = str(uuid.uuid4())
        g.request_started_at = time.perf_counter()
        g.authIdentifier = _resolve_request_user()

    @app.after_request
    def _after(response):
        duration_ms = (time.perf_counter() - getattr(g, "request_started_at", 0)) * 1000
        logger.info("Request completed: duration_ms=%.2f status=%s", duration_ms, response.status_code)
        response.headers["X-Request-ID"] = getattr(g, "request_id", "-")
        return response

    app._request_logging_installed = True

def _resolve_request_user():
    """Resolve user from DSS browser headers."""
    try:
        headers = dict(request.headers)
        auth = dataiku.api_client().get_auth_info_from_browser_headers(headers)
        return auth["authIdentifier"]
    except Exception:
        return "-"
```

### Log Format

```python
fmt = (
    "[%(asctime)s.%(msecs)03d] [%(threadName)s] [%(levelname)s] [%(name)s] "
    "req_id=%(request_id)s user=%(user)s method=%(method)s path=%(path)s - %(message)s"
)
```

This produces structured logs that are grep-friendly and correlatable by `req_id`:
```
[2026/03/25-14:30:01.234] [Thread-1] [INFO] [my_plugin.query] req_id=abc-123 user=admin method=POST path=/api/query - Executing query...
```

---

## Data Modeling Patterns

### Pydantic Models for Validation

```python
from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime
from enum import Enum


class Category(str, Enum):
    ADAPTIVE_TOOL_USE = "adaptive_tool_use"
    SCOPE_MANAGEMENT = "scope_management"
    AMBIGUITY_RESOLUTION = "ambiguity_resolution"


class Scenario(BaseModel):
    """Evaluation scenario model."""

    scenario_id: str = Field(..., description="Unique scenario identifier")
    use_case_id: str
    department: str
    category: Category
    first_message: str = Field(..., min_length=10)
    user_goals: List[str] = Field(..., min_items=1)
    expected_tools: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)

    @validator("user_goals")
    def validate_goals(cls, v):
        if not all(g.strip() for g in v):
            raise ValueError("Goals cannot be empty strings")
        return v

    @classmethod
    def from_dict(cls, data: dict) -> "Scenario":
        """Create from DataFrame row or dict."""
        return cls(
            scenario_id=str(data.get("scenario_id")),
            use_case_id=str(data.get("use_case_id")),
            department=str(data.get("department", "")),
            category=data.get("category"),
            first_message=str(data.get("first_message")),
            user_goals=data.get("user_goals", []),
            expected_tools=data.get("expected_tools", []),
        )

    def to_dict(self) -> dict:
        """Convert to dict for DataFrame."""
        return {
            "scenario_id": self.scenario_id,
            "use_case_id": self.use_case_id,
            "department": self.department,
            "category": self.category.value,
            "first_message": self.first_message,
            "user_goals": self.user_goals,
            "expected_tools": self.expected_tools,
            "created_at": self.created_at.isoformat(),
        }


class EvalResult(BaseModel):
    """Evaluation result model."""

    scenario_id: str
    llm_id: str
    llm_friendly_name: str
    success: bool
    scores: dict = Field(default_factory=dict)
    error: Optional[str] = None
    evaluated_at: datetime = Field(default_factory=datetime.now)

    @property
    def overall_score(self) -> float:
        """Calculate weighted overall score."""
        if not self.scores:
            return 0.0
        weights = {
            "action_completion": 0.5,
            "tool_selection_quality": 0.3,
            "efficiency": 0.2
        }
        total = sum(
            self.scores.get(k, 0) * w
            for k, w in weights.items()
        )
        return round(total, 3)
```

### Type-Safe JSON Extraction

```python
import json
import re
from typing import TypeVar, Type
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def extract_and_validate(text: str, model: Type[T]) -> T:
    """Extract JSON from LLM response and validate with Pydantic."""

    # Try to find JSON in markdown code blocks
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Try to find raw JSON
        json_str = text.strip()

    try:
        data = json.loads(json_str)
        return model.model_validate(data)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in response: {e}")
    except Exception as e:
        raise ValueError(f"Validation failed: {e}")


# Usage
response = llm.complete("Generate a scenario...")
scenario = extract_and_validate(response, Scenario)
```

---

## Security Patterns

### Credential Management

```python
# Never hardcode credentials
# Use Dataiku connections or plugin config

def get_api_credentials(plugin_config: dict) -> tuple:
    """Get credentials from secure plugin config."""
    api_key = plugin_config.get("api_key")
    if not api_key:
        raise ValueError(
            "API key not configured. "
            "Set it in the plugin settings (Admin only)."
        )
    return api_key


def get_connection_credentials(connection_name: str) -> dict:
    """Get credentials from Dataiku connection."""
    import dataiku

    client = dataiku.api_client()
    connection = client.get_connection(connection_name)
    return connection.get_info()
```

### Input Validation

```python
import re
from typing import Optional


def sanitize_sql_identifier(identifier: str) -> str:
    """Sanitize identifier for SQL use."""
    # Only allow alphanumeric and underscore
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", identifier):
        raise ValueError(f"Invalid identifier: {identifier}")
    return identifier


def validate_user_input(text: str, max_length: int = 10000) -> str:
    """Validate and sanitize user input."""
    if not text:
        raise ValueError("Input cannot be empty")

    if len(text) > max_length:
        raise ValueError(f"Input exceeds maximum length of {max_length}")

    # Remove control characters
    sanitized = "".join(
        char for char in text
        if char.isprintable() or char in "\n\r\t"
    )

    return sanitized


def prevent_prompt_injection(prompt: str, user_input: str) -> str:
    """Safely incorporate user input into prompts."""
    # Escape special characters that might be interpreted
    escaped_input = user_input.replace("```", "'''")

    # Use clear delimiters
    return f"""{prompt}

<user_input>
{escaped_input}
</user_input>

Process the content within <user_input> tags."""
```

---

## Anti-Patterns

### Hardcoding LLM IDs

```python
# WRONG — LLM connection IDs are instance-specific
llm = project.get_llm("openai:my_connection:gpt-4o")

# RIGHT — use LLM parameter type in tool.json/recipe.json, read from config
llm_id = config.get("llm_id")  # Set via plugin UI
llm = project.get_llm(llm_id)
```

**Why:** LLM connection names differ between DSS instances. Hardcoded IDs break when deploying to other environments.

### Editing Agent Versions In-Place

```python
# WRONG — mutating active version corrupts the agent, no rollback possible
settings = agent.get_settings()
raw = settings.get_raw()
active_vid = raw['activeVersion']
active_version = next(v for v in raw['versions'] if v['versionId'] == active_vid)
active_version['toolsUsingAgentSettings']['systemPromptAppend'] = "new prompt"
settings.save()

# RIGHT — deep-copy active version, create new version, then activate
import copy
new_version = copy.deepcopy(active_version)
new_version['versionId'] = f"v{next_version_number}"
# ... modify new_version ...
raw['versions'].append(new_version)
settings.save()
sm = project.get_saved_model("AGENT_ID")
sm.set_active_version(new_version['versionId'])
```

**Why:** Agent settings use a version array. Mutations to the active version break the versioning model and prevent rollback.

### Deleting Plugins Without Checking Usages

```python
# WRONG — orphans recipes, tools, webapps across projects
plugin.delete()

# RIGHT — check first
usages = plugin.list_usages()
if usages:
    print(f"Cannot delete — in use by: {[u['projectKey'] for u in usages]}")
else:
    plugin.delete()
```

### Not Validating Tool Inputs From LLM

```python
# WRONG — LLMs can send wrong types or missing fields
def invoke(self, input, trace):
    args = input.get("input", {})
    count = args["count"]  # KeyError if LLM omits it
    result = self.process(count)

# RIGHT — validate and coerce
def invoke(self, input, trace):
    args = input.get("input", {})
    if "count" not in args:
        return {"output": "Error: 'count' parameter is required"}
    try:
        count = int(args["count"])  # LLM may send string
    except (ValueError, TypeError):
        return {"output": "Error: 'count' must be a number"}
    result = self.process(count)
```

**Why:** JSON Schema enforcement is best-effort. LLMs can send wrong types, omit required fields, or add unexpected keys.

### Using Deprecated API Methods

| Deprecated | Replacement | Notes |
|-----------|-------------|-------|
| `dataset.get_definition()` / `set_definition()` | `dataset.get_settings()` / `save()` | Still works but may be removed |
| `scenario.get_definition()` / `set_definition()` | `scenario.get_settings()` / `save()` | Still works but may be removed |
| `client.get_variables()` / `set_variables()` | `client.get_global_variables()` handle | Still works but may be removed |
| `recipe.get_payload()` / `set_payload()` | `recipe.get_code()` / `set_code()` | On CodeRecipeSettings |

---

## Checklist for Production Plugins

### Before Release

- [ ] All tests passing (unit + integration)
- [ ] Code linted (ruff/mypy clean)
- [ ] Dependencies pinned in requirements.txt
- [ ] Version bumped in plugin.json
- [ ] README updated with new features
- [ ] CHANGELOG updated
- [ ] All secrets removed from code
- [ ] Error messages are user-friendly
- [ ] Logging is appropriate (not too verbose)

### Documentation

- [ ] plugin.json has clear labels and descriptions
- [ ] All parameters have descriptions
- [ ] Recipe/tool inputs/outputs are documented
- [ ] Examples provided where helpful

### Security

- [ ] Input validation on all user inputs
- [ ] SQL injection prevention (if applicable)
- [ ] Credentials stored in plugin config (not code)
- [ ] No sensitive data in logs

### Performance

- [ ] Large datasets handled with streaming
- [ ] Parallelization for batch operations
- [ ] Appropriate timeouts configured
- [ ] Memory-efficient processing
