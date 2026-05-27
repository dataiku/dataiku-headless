# Dataiku Python API

Reference for the `dataiku` and `dataikuapi` Python packages used in code recipes, notebooks, scenarios, and plugins.

## API Introspection

When a method isn't in this reference, discover it directly:

```python
import inspect, dataikuapi

# List methods on any object
print([m for m in dir(project) if not m.startswith('_')])

# Get docstring for a specific method
print(inspect.getdoc(dataikuapi.DSSClient.list_projects))
```

## Two Packages, Two Purposes

| Package | Import | Purpose | Available In |
|---------|--------|---------|-------------|
| `dataiku` | `import dataiku` | In-context API (recipes, notebooks, webapps) | Inside DSS |
| `dataikuapi` | `import dataikuapi` | Admin/remote API (external scripts, CI/CD) | Anywhere with API key |

## dataiku.Dataset — Reading & Writing Data

### Basic Read

```python
import dataiku
import pandas as pd

dataset = dataiku.Dataset("my_dataset")

# Read entire dataset as DataFrame
df = dataset.get_dataframe()

# Read with options
df = dataset.get_dataframe(
    columns=["col_a", "col_b"],   # Select specific columns
    sampling="head",               # "head", "random", "full"
    limit=10000,                   # Row limit
    infer_with_pandas=False        # Use DSS schema (default)
)
```

### Fast-Path Read (DSS 13+)

Optimized for Parquet on S3 and Snowflake — significantly faster for wide datasets.

```python
df = dataset.get_fast_path_dataframe(columns=["col_a", "col_b"])
```

### Memory-Efficient Read Options

```python
df = dataset.get_dataframe(
    disable_type_checking=True,          # Skip thorough data checks
    categorical_columns=["status"],       # Read as pandas Categorical
    nullable_integer_columns=["count"],   # Use pd.Int64Dtype for NaN-safe ints
    override_dtypes={"big_col": "float32"} # Reduce memory with smaller types
)
```

### Streaming Read (Large Datasets)

```python
# Iterate in chunks — never loads entire dataset in memory
for chunk_df in dataset.iter_dataframes(chunksize=50000):
    process(chunk_df)

# Iterate row by row (slower, minimal memory)
for row in dataset.iter_rows():
    print(row)  # dict-like object
```

### Write Data

```python
output = dataiku.Dataset("output_dataset")

# Write DataFrame with automatic schema inference
output.write_with_schema(df)

# Write DataFrame using existing schema (faster, no schema change)
output.write_dataframe(df)
```

### Streaming Write (Large Results)

```python
output = dataiku.Dataset("output_dataset")

output.write_schema([
    {"name": "id", "type": "int"},
    {"name": "value", "type": "double"},
    {"name": "label", "type": "string"}
])

with output.get_writer() as writer:
    for chunk_df in process_in_chunks():
        writer.write_dataframe(chunk_df)
```

### Schema Management

```python
dataset = dataiku.Dataset("my_dataset")

# Read schema
schema = dataset.read_schema()
# [{"name": "col_a", "type": "string"}, {"name": "col_b", "type": "int"}, ...]

# Write schema (before writing data)
dataset.write_schema([
    {"name": "id", "type": "bigint"},
    {"name": "name", "type": "string"},
    {"name": "amount", "type": "double"},
    {"name": "created_at", "type": "date"}
])
```

### Partitioned Datasets

```python
dataset = dataiku.Dataset("partitioned_dataset")

# List partitions
partitions = dataset.list_partitions()

# Read specific partition
df = dataset.get_dataframe(partitions=["2024-01-15"])

# Write to specific partition
dataset.set_write_partition("2024-01-15")
dataset.write_with_schema(df)
```

## Code Recipe Patterns

### Standard Recipe Structure

```python
import dataiku
import pandas as pd

# Get input/output dataset names (defined in recipe UI)
input_name = get_input_names_for_role("input_dataset")[0]
output_name = get_output_names_for_role("output_dataset")[0]

# Read
input_df = dataiku.Dataset(input_name).get_dataframe()

# Transform
result_df = input_df.copy()
result_df["new_col"] = result_df["amount"] * 1.1

# Write
dataiku.Dataset(output_name).write_with_schema(result_df)
```

### Multiple Inputs/Outputs

```python
main_name = get_input_names_for_role("main_data")[0]
lookup_name = get_input_names_for_role("lookup_table")[0]

main_df = dataiku.Dataset(main_name).get_dataframe()
lookup_df = dataiku.Dataset(lookup_name).get_dataframe()

merged = main_df.merge(lookup_df, on="key_column", how="left")
```

### Recipe with Managed Folder Input

```python
import dataiku
import json

folder_name = get_input_names_for_role("input_folder")[0]
folder = dataiku.Folder(folder_name)

# List files
files = folder.list_paths_in_partition()

# Read a file
with folder.get_download_stream("data/config.json") as f:
    config = json.load(f)

# Read all CSVs
import pandas as pd
dfs = []
for path in folder.list_paths_in_partition():
    if path.endswith(".csv"):
        with folder.get_download_stream(path) as f:
            dfs.append(pd.read_csv(f))
combined = pd.concat(dfs, ignore_index=True)
```

## dataiku.Folder — Managed Folder Operations

```python
folder = dataiku.Folder("my_folder")

# List contents
paths = folder.list_paths_in_partition()

# Read file
with folder.get_download_stream("report.pdf") as stream:
    content = stream.read()

# Write file
folder.upload_stream("output/result.json", json.dumps(data).encode())

# Write from file path
folder.upload_file("output/image.png", "/tmp/generated_image.png")

# Delete file
folder.delete_path("old_file.csv")

# Get folder info
info = folder.get_info()
```

## Project Variables

### In Recipes and Notebooks

```python
import dataiku

# Get all custom variables (includes project + global)
vars = dataiku.get_custom_variables()          # all as strings
vars_typed = dataiku.get_custom_variables(typed=True)  # preserve types

threshold = vars_typed["quality_threshold"]  # int/float preserved
mode = vars["pipeline_mode"]                 # always string
```

### Via Project API (Read/Write)

```python
client = dataiku.api_client()
project = client.get_default_project()

# Read
variables = project.get_variables()
standard = variables["standard"]   # shared across instances
local = variables["local"]         # instance-specific

# Write
variables["standard"]["last_run"] = "2024-01-15"
project.set_variables(variables)
```

## SQL Execution

### SQLExecutor2

```python
import dataiku

executor = dataiku.sql.SQLExecutor2(connection="my_postgres")

# Query returning results
df = executor.query_to_df("SELECT * FROM users WHERE active = true LIMIT 100")

# Execute statement (no results)
executor.query_to_df("TRUNCATE TABLE staging_table")

# Parameterized queries (prevent SQL injection)
df = executor.query_to_df(
    "SELECT * FROM users WHERE department = %s AND active = %s",
    params=["engineering", True]
)
```

### SQL on Dataset's Connection

```python
dataset = dataiku.Dataset("my_sql_dataset")
executor = dataiku.sql.SQLExecutor2(dataset=dataset)

df = executor.query_to_df("SELECT COUNT(*) as cnt FROM ${DKU_DST_my_sql_dataset}")
```

## dataikuapi.DSSClient — Admin/Remote API

### Connection

```python
import dataikuapi

# Connect to DSS instance
client = dataikuapi.DSSClient("https://dss.example.com", "your-api-key")

# Inside DSS (no key needed)
import dataiku
client = dataiku.api_client()
```

### Project Operations

```python
projects = client.list_project_keys()

project = client.get_project("MY_PROJECT")

new_project = client.create_project("NEW_PROJECT", "My New Project", "admin")

with open("project_export.zip", "wb") as f:
    project.export_to_stream(f)
```

### Dataset Operations

```python
project = client.get_project("MY_PROJECT")

datasets = project.list_datasets()
for ds in datasets:
    print(f"{ds['name']} ({ds['type']})")

ds = project.get_dataset("customers")
settings = ds.get_settings()
metadata = ds.get_metadata()
```

### Recipe Operations

```python
recipes = project.list_recipes()

recipe = project.get_recipe("compute_features")
settings = recipe.get_settings()

job = recipe.run()
job.wait_for_completion()
status = job.get_status()  # "DONE", "FAILED", "ABORTED"
```

### User Management

```python
users = client.list_users()

client.create_user("new_user", "password123", display_name="New User",
                   groups=["data-analysts"])

user = client.get_user("username")
settings = user.get_settings()
```

## Connections & Dataset Creation

### Create Dataset Programmatically

```python
# Create SQL dataset
project.create_dataset("sql_table", "PostgreSQL", params={
    "connection": "my_postgres",
    "table": "public.my_table",
    "schema": "public"
})

# Create S3 dataset
project.create_dataset("s3_data", "S3", params={
    "connection": "my_s3",
    "bucket": "my-bucket",
    "path": "/data/output/",
    "filesSelectionRules": {"mode": "ALL"}
})
```

## Code Environments

```python
envs = client.list_code_envs()

env = client.get_code_env("PYTHON", "my-env")

definition = env.get_definition()
definition["desc"]["installCorePackages"] = False
env.set_definition(definition)

env.update_packages()
```

On Python 3.11+, use the canonical code-environment package policy in `code-environments.md`.

## Common Patterns

### Chunked Processing for Large Datasets

```python
input_ds = dataiku.Dataset("large_input")
output_ds = dataiku.Dataset("output")

output_ds.write_schema(input_ds.read_schema())

with output_ds.get_writer() as writer:
    for chunk in input_ds.iter_dataframes(chunksize=100000):
        processed = transform(chunk)
        writer.write_dataframe(processed)
```

### Schema Inference from DataFrame

```python
def df_to_dku_schema(df):
    type_map = {
        "int64": "bigint", "int32": "int",
        "float64": "double", "float32": "float",
        "object": "string", "bool": "boolean",
        "datetime64[ns]": "date"
    }
    return [
        {"name": col, "type": type_map.get(str(df[col].dtype), "string")}
        for col in df.columns
    ]
```

### Partition Handling in Recipes

```python
input_ds = dataiku.Dataset("partitioned_input")
output_ds = dataiku.Dataset("partitioned_output")

# Read only the partition DSS tells you to process
df = input_ds.get_dataframe()  # automatically filtered to current partition

# Write to matching output partition (automatic)
output_ds.write_with_schema(result_df)
```

### Error-Safe Dataset Operations

```python
def safe_read(dataset_name, **kwargs):
    try:
        ds = dataiku.Dataset(dataset_name)
        df = ds.get_dataframe(**kwargs)
        if df.empty:
            print(f"WARNING: Dataset '{dataset_name}' returned 0 rows")
        return df
    except Exception as e:
        raise RuntimeError(f"Failed to read dataset '{dataset_name}': {e}")
```

## Quick Reference

| Operation | Code |
|-----------|------|
| Read DataFrame | `dataiku.Dataset("name").get_dataframe()` |
| Write DataFrame | `dataiku.Dataset("name").write_with_schema(df)` |
| Stream read | `for chunk in ds.iter_dataframes(chunksize=N):` |
| Read schema | `ds.read_schema()` |
| Get variables | `dataiku.get_custom_variables(typed=True)` |
| Set variables | `project.set_variables(vars)` |
| SQL query | `SQLExecutor2(connection="conn").query_to_df(sql)` |
| Folder read | `folder.get_download_stream("path")` |
| Folder write | `folder.upload_stream("path", data)` |
| Recipe inputs | `get_input_names_for_role("role")[0]` |
| Recipe outputs | `get_output_names_for_role("role")[0]` |
| API client (inside DSS) | `dataiku.api_client()` |
| API client (external) | `dataikuapi.DSSClient(url, key)` |
