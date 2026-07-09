---
name: download-recipe-settings-and-payload-reference
description: "Settings and params reference for download recipes, including source providers and file synchronization flags."
---

# Download Recipe Settings And Payload Reference

Use this reference for `download` recipe edits (`get_recipe_settings` + `set_recipe_settings` action `set_params`).

## Observed Settings Shape

In these recipes:

- `params` controls behavior.
- `payload` is not used (`payload_error` observed when reading JSON payload).
- `inputs` was empty; source definitions are in `params.sources`.
- `outputs` contained one managed folder.

Observed top-level params keys:

- `deleteExtraFiles`
- `copyEvenUpToDateFiles`
- `sources`
- `variablesExpansionLoopConfig`

## Top-Level Params Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `deleteExtraFiles` | no | `boolean` | If true, remove destination files not present at source. |
| `copyEvenUpToDateFiles` | no | `boolean` | If true, recopy files even when unchanged. |
| `sources` | yes | `list<object>` | Download source definitions. |
| `variablesExpansionLoopConfig` | no | `object` | Variable expansion loop settings (disabled in observed recipes). |

## `sources[]` Matrix

| Param | Required | Domain | Notes |
| --- | --- | --- | --- |
| `providerType` | yes | `enum` | Observed: `S3`, `URL`. Also allowed: `Filesystem`, `HDFS`, `Azure`, `S3`, `GCS`, `FTP`, `SFTP`, `SCP`, `DatabricksVolume`. |
| `useGlobalProxy` | no | `boolean` | Proxy behavior toggle. |
| `params` | yes | `object` | Provider-specific source config. |

## Provider-Specific `sources[i].params` (Observed)

S3 source params:

- `path`
- `connection` (`string<connection_name>`, must be a Dataiku connection name)
- `consider404AsEmpty`
- `fallbackHeadToGet`
- `trustAnySSLCertificate`

URL source params:

- `path` (full URL)
- `consider404AsEmpty`
- `fallbackHeadToGet`
- `trustAnySSLCertificate`

Additional supported provider types (beyond the two observed examples above):

- `Filesystem`
- `HDFS`
- `Azure`
- `GCS`
- `FTP`
- `SFTP`
- `SCP`
- `DatabricksVolume`

## Canonical Params Examples (Trimmed)

### Download from S3 managed connection

```json
{
  "deleteExtraFiles": true,
  "copyEvenUpToDateFiles": false,
  "sources": [
    {
      "providerType": "S3",
      "useGlobalProxy": true,
      "params": {
        "path": "/your/sub/path/",
        "connection": "s3-managed",
        "consider404AsEmpty": true,
        "fallbackHeadToGet": true,
        "trustAnySSLCertificate": false
      }
    }
  ],
  "variablesExpansionLoopConfig": {
    "enabled": false,
    "mode": "CREATE_VARIABLE_FOR_EACH_COLUMN",
    "replacements": []
  }
}
```

### Download from URL with force recopy

```json
{
  "deleteExtraFiles": false,
  "copyEvenUpToDateFiles": true,
  "sources": [
    {
      "providerType": "URL",
      "useGlobalProxy": true,
      "params": {
        "path": "https://data.wa.gov/api/views/f6w7-q2d2/rows.csv?accessType=DOWNLOAD",
        "consider404AsEmpty": true,
        "fallbackHeadToGet": true,
        "trustAnySSLCertificate": true
      }
    }
  ],
  "variablesExpansionLoopConfig": {
    "enabled": false,
    "mode": "CREATE_VARIABLE_FOR_EACH_COLUMN",
    "replacements": []
  }
}
```

## Recommended Update Pattern

1. Read current settings with `get_recipe_settings`.
2. Copy current `params`.
3. Edit only intended blocks (`sources`, sync flags, variable-loop block).
4. Write params with `set_recipe_settings` action `set_params`.
5. Re-read settings to confirm only intended keys changed.
