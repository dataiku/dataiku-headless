---
name: prepare-python-udf
description: "Observed JSON patterns for the PythonUDF prepare/shaker processor."
---

# PythonUDF Processor

Run user-defined Python over each cell/row/row group via `process` function. `useKernel` true=needs Python code env; else in-process Jython (Python 2, stdlib only).

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `mode` | yes | `enum` | `CELL` \| `ROW` \| `MULTI_ROWS` | `CELL`=one value per row (needs `column`); `ROW`=returns dict replacing row; `MULTI_ROWS`=returns iterable of rows (changes row count). |
| `pythonSourceCode` | yes | `string<any>` | Python source defining `def process(...)` | Entry-point function always `process`. Runs under Jython unless `useKernel` is `true`. |
| `column` | conditional | `string<column_name>` | Any valid output column name | Output column for `CELL`; required when `mode` is `CELL`. Unused for `ROW`/`MULTI_ROWS`. |
| `errorColumn` | no | `string<column_name>` | Any valid output column name | Optional column capturing per-row error messages. |
| `stopOnError` | no | `boolean` | `true` \| `false` | Stop processor on first error raised by code. |
| `usePythonUnicode` | no | `boolean` | `true` \| `false` | Pass cell values as unicode (needed for non-ASCII text). |
| `useKernel` | no | `boolean` | `true` \| `false` | `true`=real Python process from code env (full libraries, vectorization); else in-process Jython. |
| `vectorize` | no | `boolean` | `true` \| `false` | Meaningful only when `useKernel` is `true`; passes pandas DataFrame batch to `process` instead of one value/row. |
| `vectorSize` | no | `integer` | Any positive integer | Batch size for vectorized kernel communication. |
| `sourceColumnsList` | no | `list<string<column_name>>` | Any list of input column names | Explicit list of used input columns (kernel mode) for faster processing. |
| `sourceColumnsPattern` | no | `string<regex>` | Any valid Java regex | Regex selecting used input columns (kernel mode). |
| `envSelection` | conditional | `object<{envMode:enum, envName:string<any>}>` | `envMode` in `USE_BUILTIN_MODE` \| `INHERIT` \| `EXPLICIT_ENV` | Picks Python code env when `useKernel` is `true` (non-remote); `EXPLICIT_ENV` requires `envName`. |
| `fixedEnvName` | no | `string<any>` | Any valid Python code-env name | Code env for remote/Yarn execution only; ignored locally (local uses `envSelection`). |

## Canonical Variant

```json
{
  "type": "PythonUDF",
  "params": {
    "mode": "CELL",
    "stopOnError": false,
    "pythonSourceCode": "def process(value):\n    if value is None:\n        return 0\n    return len(value)\n",
    "useKernel": false,
    "column": "free_text_length",
    "errorColumn": "free_text_udf_error",
    "sourceColumnsList": ["free_text"],
    "usePythonUnicode": true,
    "vectorSize": 256,
    "vectorize": false
  }
}
```
