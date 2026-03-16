# Testing & Debugging Guide

> Complete reference for testing Dataiku plugins: unit tests, integration tests, CI/CD, and debugging strategies.

---

## Testing Strategy

### Test Pyramid for Plugins

```
        ┌───────────┐
        │   E2E     │  ← Playwright/Selenium for webapps
        │   Tests   │
        ├───────────┤
        │Integration│  ← Tests against DSS instance
        │   Tests   │
        ├───────────┤
        │   Unit    │  ← Fast, isolated tests
        │   Tests   │
        └───────────┘
```

| Level | Speed | Isolation | Coverage Focus |
|-------|-------|-----------|----------------|
| Unit | Fast | Full mock | Business logic |
| Integration | Medium | DSS instance | API interactions |
| E2E | Slow | None | User workflows |

---

## Unit Testing

### Project Structure

```
my-plugin/
├── python-lib/
│   └── my_plugin/
│       ├── __init__.py
│       └── utils.py
├── custom-recipes/
│   └── my-recipe/
│       ├── recipe.json
│       └── recipe.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # pytest fixtures
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_utils.py
│   │   └── test_recipe.py
│   └── integration/
│       └── test_flow.py
├── pytest.ini
└── pyproject.toml
```

### pytest.ini

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_functions = test_*
addopts = -v --tb=short
markers =
    unit: Unit tests (fast, no DSS)
    integration: Integration tests (requires DSS)
    slow: Slow tests
```

### conftest.py - Fixtures

```python
# tests/conftest.py
import pytest
from unittest.mock import Mock, MagicMock, patch
import pandas as pd


@pytest.fixture
def mock_dataiku():
    """Mock the dataiku module."""
    with patch.dict("sys.modules", {"dataiku": MagicMock()}):
        import dataiku
        yield dataiku


@pytest.fixture
def mock_dataset():
    """Create a mock Dataset object."""
    dataset = Mock()
    dataset.get_dataframe.return_value = pd.DataFrame({
        "id": [1, 2, 3],
        "name": ["Alice", "Bob", "Charlie"],
        "value": [100, 200, 300]
    })
    dataset.read_schema.return_value = [
        {"name": "id", "type": "int"},
        {"name": "name", "type": "string"},
        {"name": "value", "type": "int"}
    ]
    return dataset


@pytest.fixture
def mock_llm():
    """Create a mock LLM object."""
    llm = Mock()
    completion = Mock()
    completion.execute.return_value = Mock(text="Mock LLM response")
    llm.new_completion.return_value = completion
    return llm


@pytest.fixture
def mock_api_client(mock_llm):
    """Create a mock API client."""
    client = Mock()
    project = Mock()
    project.get_llm.return_value = mock_llm
    project.list_llms.return_value = [
        {"id": "openai:gpt-4", "friendlyName": "GPT-4"}
    ]
    client.get_default_project.return_value = project
    return client


@pytest.fixture
def sample_config():
    """Sample recipe configuration."""
    return {
        "llm_id": "openai:gpt-4",
        "batch_size": 10,
        "temperature": 0.7,
        "max_concurrent": 4
    }
```

### Unit Test Examples

```python
# tests/unit/test_utils.py
import pytest
from my_plugin.utils import extract_json, sanitize_string, call_llm


class TestExtractJson:
    """Tests for JSON extraction utility."""

    def test_extracts_json_from_markdown(self):
        text = '''Here is the result:
        ```json
        {"key": "value", "count": 42}
        ```
        '''
        result = extract_json(text)
        assert result == {"key": "value", "count": 42}

    def test_extracts_json_array(self):
        text = '[{"id": 1}, {"id": 2}]'
        result = extract_json(text, expect_array=True)
        assert len(result) == 2

    def test_handles_invalid_json(self):
        text = "not valid json"
        with pytest.raises(ValueError):
            extract_json(text)

    @pytest.mark.parametrize("input,expected", [
        ('{"a": 1}', {"a": 1}),
        ('  {"a": 1}  ', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
    ])
    def test_various_formats(self, input, expected):
        assert extract_json(input) == expected


class TestSanitizeString:
    """Tests for string sanitization."""

    def test_removes_control_characters(self):
        result = sanitize_string("hello\x00world")
        assert "\x00" not in result

    def test_preserves_normal_text(self):
        text = "Hello, World! 123"
        assert sanitize_string(text) == text


class TestCallLlm:
    """Tests for LLM calling utility."""

    def test_successful_call(self, mock_llm):
        result = call_llm(mock_llm, "Test prompt")
        assert result == "Mock LLM response"
        mock_llm.new_completion.assert_called_once()

    def test_handles_error(self, mock_llm):
        mock_llm.new_completion.side_effect = Exception("API Error")
        with pytest.raises(Exception):
            call_llm(mock_llm, "Test prompt")
```

### Testing Recipes

```python
# tests/unit/test_recipe.py
import pytest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd


class TestMyRecipe:
    """Tests for custom recipe logic."""

    @pytest.fixture
    def mock_recipe_env(self, mock_dataset, sample_config):
        """Setup mocked recipe environment."""
        with patch("dataiku.customrecipe.get_recipe_config") as mock_config, \
             patch("dataiku.customrecipe.get_input_names_for_role") as mock_input, \
             patch("dataiku.customrecipe.get_output_names_for_role") as mock_output, \
             patch("dataiku.Dataset") as mock_ds_class:

            mock_config.return_value = sample_config
            mock_input.return_value = ["input_dataset"]
            mock_output.return_value = ["output_dataset"]
            mock_ds_class.return_value = mock_dataset

            yield {
                "config": mock_config,
                "input": mock_input,
                "output": mock_output,
                "dataset": mock_ds_class
            }

    def test_recipe_processes_data(self, mock_recipe_env, mock_api_client):
        """Test that recipe processes input data correctly."""
        with patch("dataiku.api_client", return_value=mock_api_client):
            # Import recipe module (after mocks are set up)
            from custom_recipes.my_recipe import recipe

            # Verify interactions
            mock_recipe_env["dataset"].assert_called()

    def test_recipe_handles_empty_input(self, mock_recipe_env):
        """Test recipe handles empty dataset gracefully."""
        mock_recipe_env["dataset"].return_value.get_dataframe.return_value = pd.DataFrame()

        # Should not raise
        from custom_recipes.my_recipe import recipe

    def test_parallel_processing(self, mock_recipe_env, mock_api_client):
        """Test parallel processing works correctly."""
        # Create larger dataset
        large_df = pd.DataFrame({
            "id": range(100),
            "text": [f"Text {i}" for i in range(100)]
        })
        mock_recipe_env["dataset"].return_value.get_dataframe.return_value = large_df

        with patch("dataiku.api_client", return_value=mock_api_client):
            from custom_recipes.my_recipe import recipe
            # Verify all rows were processed
```

### Testing Agent Tools

```python
# tests/unit/test_agent_tool.py
import pytest
from unittest.mock import Mock, patch

from python_agent_tools.my_tool.tool import MyTool


class TestMyTool:
    """Tests for custom agent tool."""

    @pytest.fixture
    def tool(self):
        """Create configured tool instance."""
        tool = MyTool()
        tool.set_config(
            config={"param1": "value1", "max_results": 10},
            plugin_config={"api_key": "test-key"}
        )
        return tool

    def test_get_descriptor_returns_valid_schema(self, tool):
        """Test tool descriptor is valid."""
        descriptor = tool.get_descriptor(None)

        assert "description" in descriptor
        assert "inputSchema" in descriptor
        assert descriptor["inputSchema"]["type"] == "object"
        assert "properties" in descriptor["inputSchema"]

    def test_invoke_success(self, tool):
        """Test successful tool invocation."""
        result = tool.invoke(
            input={"input": {"query": "test query"}},
            trace=None
        )

        assert "output" in result
        assert isinstance(result["output"], str)

    def test_invoke_missing_required_param(self, tool):
        """Test tool handles missing parameters."""
        result = tool.invoke(
            input={"input": {}},  # Missing required 'query'
            trace=None
        )

        assert "error" in result["output"].lower() or "required" in result["output"].lower()

    def test_invoke_with_trace(self, tool):
        """Test tool adds metadata to trace."""
        trace = Mock()

        tool.invoke(
            input={"input": {"query": "test"}},
            trace=trace
        )

        # Verify trace was used (if your tool uses it)
        # trace.add_metadata.assert_called()
```

---

## Integration Testing

### Setup with dataiku-plugin-tests-utils

```bash
pip install dataiku-plugin-tests-utils
```

### conftest.py for Integration

```python
# tests/integration/conftest.py
import pytest
import os


@pytest.fixture(scope="session")
def dss_client():
    """Get DSS client for integration tests."""
    import dataiku

    # Use environment variables for connection
    host = os.environ.get("DSS_HOST", "http://localhost:11200")
    api_key = os.environ.get("DSS_API_KEY")

    dataiku.set_remote_dss(host, api_key)
    return dataiku.api_client()


@pytest.fixture(scope="session")
def test_project(dss_client):
    """Get or create test project."""
    project_key = os.environ.get("DSS_TEST_PROJECT", "PLUGIN_TEST")

    try:
        project = dss_client.get_project(project_key)
    except:
        project = dss_client.create_project(project_key, "Plugin Test Project")

    yield project

    # Optional: cleanup after tests
    # project.delete()


@pytest.fixture
def test_dataset(test_project):
    """Create a test dataset."""
    import pandas as pd

    ds_name = "test_dataset"

    # Create dataset
    builder = test_project.new_dataset(ds_name, "Filesystem")
    ds = builder.create()

    # Write test data
    df = pd.DataFrame({
        "id": [1, 2, 3],
        "name": ["Alice", "Bob", "Charlie"]
    })

    import dataiku
    dataiku.Dataset(ds_name).write_with_schema(df)

    yield ds

    # Cleanup
    ds.delete()
```

### Integration Test Examples

```python
# tests/integration/test_recipe_integration.py
import pytest


@pytest.mark.integration
class TestRecipeIntegration:
    """Integration tests for recipe against real DSS."""

    def test_recipe_creates_output(self, test_project, test_dataset):
        """Test recipe produces expected output."""
        import dataiku

        # Create recipe
        recipe_creator = test_project.new_recipe("my-plugin_my-recipe")
        recipe_creator.set_input("input_dataset", test_dataset.name)
        recipe_creator.set_output("output_dataset", "test_output")
        recipe = recipe_creator.create()

        # Run recipe
        job = recipe.run()
        job.wait_for_completion()

        assert job.get_status() == "DONE"

        # Verify output
        output = dataiku.Dataset("test_output").get_dataframe()
        assert len(output) > 0

    def test_recipe_with_parameters(self, test_project, test_dataset):
        """Test recipe with custom parameters."""
        recipe = test_project.get_recipe("my_recipe")
        settings = recipe.get_settings()

        # Update parameters
        settings.obj["params"]["batch_size"] = 5
        settings.save()

        # Run and verify
        job = recipe.run()
        job.wait_for_completion()

        assert job.get_status() == "DONE"
```

---

## E2E Testing for Webapps

### Playwright Setup

```bash
npm install -D @playwright/test
npx playwright install
```

### playwright.config.ts

```typescript
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60000,
  use: {
    baseURL: process.env.DSS_URL || 'http://localhost:11200',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
});
```

### E2E Test Example

```typescript
// tests/e2e/webapp.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Dashboard Webapp', () => {
  test.beforeEach(async ({ page }) => {
    // Login to DSS
    await page.goto('/login');
    await page.fill('#username', process.env.DSS_USER || 'admin');
    await page.fill('#password', process.env.DSS_PASSWORD || 'admin');
    await page.click('button[type="submit"]');

    // Navigate to webapp
    await page.goto('/projects/TEST_PROJECT/webapps/my-webapp');
  });

  test('displays dashboard correctly', async ({ page }) => {
    // Wait for data to load
    await page.waitForSelector('.chart-container');

    // Verify chart is rendered
    const chart = await page.locator('.chart-container canvas');
    expect(await chart.isVisible()).toBe(true);
  });

  test('filters data correctly', async ({ page }) => {
    // Apply filter
    await page.selectOption('#category-filter', 'category_a');

    // Wait for update
    await page.waitForResponse('**/api/data**');

    // Verify filtered results
    const rows = await page.locator('.data-table tbody tr').count();
    expect(rows).toBeGreaterThan(0);
  });

  test('handles errors gracefully', async ({ page }) => {
    // Simulate error condition
    await page.route('**/api/data', route => route.abort());

    await page.reload();

    // Verify error message is shown
    const errorMessage = await page.locator('.error-message');
    expect(await errorMessage.isVisible()).toBe(true);
  });
});
```

---

## CI/CD Pipeline

### GitHub Actions Workflow

```yaml
# .github/workflows/plugin-ci.yml
name: Plugin CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install ruff mypy
          pip install -r code-env/python/spec/requirements.txt

      - name: Run Ruff
        run: ruff check python-lib/ custom-recipes/

      - name: Run MyPy
        run: mypy python-lib/ --ignore-missing-imports

  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install pytest pytest-cov
          pip install -r code-env/python/spec/requirements.txt
          pip install -r code-env/python/spec/requirements.dev.txt

      - name: Run unit tests
        run: pytest tests/unit -v --cov=python-lib --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml

  integration-tests:
    runs-on: ubuntu-latest
    needs: [lint, unit-tests]
    if: github.event_name == 'push'
    steps:
      - uses: actions/checkout@v4

      - name: Run integration tests
        env:
          DSS_HOST: ${{ secrets.DSS_HOST }}
          DSS_API_KEY: ${{ secrets.DSS_API_KEY }}
          DSS_TEST_PROJECT: CI_TEST
        run: |
          pip install pytest dataiku-plugin-tests-utils
          pytest tests/integration -v -m integration

  build:
    runs-on: ubuntu-latest
    needs: [unit-tests]
    steps:
      - uses: actions/checkout@v4

      - name: Build frontend
        run: |
          cd resource/frontend
          npm ci
          npm run build

      - name: Package plugin
        run: make package

      - name: Upload artifact
        uses: actions/upload-artifact@v3
        with:
          name: plugin-package
          path: dist/*.zip
```

### Makefile for CI

```makefile
.PHONY: lint test test-unit test-integration build package clean

lint:
	ruff check python-lib/ custom-recipes/
	mypy python-lib/ --ignore-missing-imports

test-unit:
	pytest tests/unit -v --cov=python-lib

test-integration:
	pytest tests/integration -v -m integration

test: test-unit

build:
	cd resource/frontend && npm ci && npm run build
	cp -r resource/frontend/dist resource/dist

package: build
	mkdir -p dist
	zip -r dist/$(shell python -c "import json; print(json.load(open('plugin.json'))['id'])").zip . \
		-x "*.git*" -x "*node_modules*" -x "*__pycache__*" -x "dist/*" -x "tests/*"

clean:
	rm -rf dist/
	rm -rf resource/dist/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
```

---

## Debugging

### Logging

```python
import logging
import sys

# Configure for DSS job logs
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr  # DSS captures stderr
)

logger = logging.getLogger(__name__)

def process_data():
    logger.info("Starting data processing")
    logger.debug(f"Config: {config}")

    try:
        result = do_something()
        logger.info(f"Processed {len(result)} items")
    except Exception as e:
        logger.exception("Processing failed")
        raise
```

### DSS Debugging Tools

```python
# In recipe or macro code
import dataiku

# Write debug info to dataset
debug_ds = dataiku.Dataset("debug_output")
debug_ds.write_with_schema(pd.DataFrame([
    {"step": "1", "data": str(intermediate_result)},
    {"step": "2", "data": str(another_result)}
]))

# Write to managed folder
folder = dataiku.Folder("debug_folder")
folder.put_file("debug.json", json.dumps(debug_data).encode())
```

### Interactive Debugging

```python
# Add breakpoint for local debugging (not in DSS)
import os
if os.environ.get("DEBUG_MODE"):
    import pdb; pdb.set_trace()
```

---

## Best Practices

### Test Organization
- Group tests by component type (recipes, tools, webapps)
- Use descriptive test names that explain the scenario
- Keep unit tests fast (< 1 second each)
- Mark slow/integration tests appropriately

### Mocking Strategy
- Mock at the boundary (Dataiku API, external services)
- Use fixtures for common mock objects
- Test both success and error paths

### CI/CD
- Run lint and unit tests on every PR
- Run integration tests on main branch only
- Cache dependencies for faster builds
- Use secrets for DSS credentials
