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
│       └── recipe.py        # Minimal: config → core → output
└── python-agent-tools/      # Tool interfaces
    └── my-tool/
        ├── tool.json
        └── tool.py          # Minimal: invoke → core → response
```

### 2. Dependency Inversion

```python
# python-lib/my_plugin/core/processor.py
from abc import ABC, abstractmethod
from typing import List, Dict


class LLMProvider(ABC):
    """Abstract LLM interface - no Dataiku dependency."""

    @abstractmethod
    def complete(self, prompt: str) -> str:
        pass


class DataProcessor:
    """Core processor using injected dependencies."""

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def process(self, items: List[Dict]) -> List[Dict]:
        """Pure business logic."""
        results = []
        for item in items:
            response = self.llm.complete(item["text"])
            results.append({**item, "response": response})
        return results


# python-lib/my_plugin/adapters/llm.py
import dataiku
from my_plugin.core.processor import LLMProvider


class DataikuLLMAdapter(LLMProvider):
    """Dataiku-specific LLM implementation."""

    def __init__(self, project, llm_id: str):
        self.llm = project.get_llm(llm_id)

    def complete(self, prompt: str) -> str:
        completion = self.llm.new_completion()
        completion.with_message(prompt, role="user")
        return completion.execute().text
```

### 3. Configuration Management

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

```python
def process_large_dataset(
    input_ds: dataiku.Dataset,
    output_ds: dataiku.Dataset,
    process_fn: Callable,
    chunk_size: int = 10000
) -> dict:
    """Process large dataset in chunks to manage memory."""
    stats = {"processed": 0, "errors": 0}
    first_chunk = True

    for chunk in input_ds.iter_dataframes(chunksize=chunk_size):
        # Process chunk
        processed_chunk = process_fn(chunk)

        # Write output
        if first_chunk:
            output_ds.write_with_schema(processed_chunk)
            first_chunk = False
        else:
            with output_ds.get_writer() as writer:
                for _, row in processed_chunk.iterrows():
                    writer.write_row_dict(row.to_dict())

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

## Documentation Patterns

### Self-Documenting Code

```python
def evaluate_scenario(
    scenario: Scenario,
    llm: LLMProvider,
    *,  # Force keyword arguments
    max_turns: int = 10,
    timeout_seconds: int = 300,
    include_trace: bool = True
) -> EvalResult:
    """
    Evaluate an LLM agent on a scenario.

    This function runs a multi-turn conversation simulation where
    a simulated user attempts to achieve their goals using the
    provided LLM agent.

    Args:
        scenario: The test scenario containing user goals and context.
        llm: The LLM provider to evaluate.
        max_turns: Maximum conversation turns before timeout (default: 10).
        timeout_seconds: Overall timeout in seconds (default: 300).
        include_trace: Whether to include full conversation trace (default: True).

    Returns:
        EvalResult containing scores and optional trace.

    Raises:
        TimeoutError: If evaluation exceeds timeout_seconds.
        LLMError: If LLM fails to respond.

    Example:
        >>> scenario = Scenario.from_dict({"scenario_id": "test", ...})
        >>> llm = DataikuLLMAdapter(project, "openai:gpt-4")
        >>> result = evaluate_scenario(scenario, llm, max_turns=5)
        >>> print(f"Score: {result.overall_score}")
    """
    ...
```

### Component Documentation

```json
// recipe.json
{
  "meta": {
    "label": "Evaluate LLM Scenarios",
    "description": "Evaluate LLM performance on predefined test scenarios. Supports multi-turn conversations, multiple LLMs in parallel, and comprehensive scoring including action completion, tool selection quality, and efficiency metrics.",
    "icon": "icon-beaker"
  },
  ...
}
```

---

## Versioning & Compatibility

### Semantic Versioning

```
MAJOR.MINOR.PATCH

MAJOR: Breaking changes (incompatible API changes)
MINOR: New features (backwards compatible)
PATCH: Bug fixes (backwards compatible)
```

### Deprecation Pattern

```python
import warnings


def old_function(arg):
    """
    Deprecated: Use new_function() instead.

    This function will be removed in version 3.0.0.
    """
    warnings.warn(
        "old_function is deprecated, use new_function instead",
        DeprecationWarning,
        stacklevel=2
    )
    return new_function(arg)


def new_function(arg):
    """The new implementation."""
    ...
```

### Feature Flags

```python
# python-lib/my_plugin/features.py

FEATURES = {
    "streaming_responses": True,
    "parallel_evaluation": True,
    "experimental_rag": False,  # Not ready for production
}


def is_enabled(feature: str) -> bool:
    """Check if a feature is enabled."""
    return FEATURES.get(feature, False)


# Usage
if is_enabled("parallel_evaluation"):
    result = parallel_evaluate(scenarios)
else:
    result = sequential_evaluate(scenarios)
```

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
