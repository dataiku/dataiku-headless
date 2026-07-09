---
name: prepare-enrich-with-record-context-processor
description: "Observed JSON patterns for the EnrichWithRecordContextProcessor prepare/shaker processor."
---

# EnrichWithRecordContextProcessor

Adds record-level source-context columns (partition id, file path/name, file record id, last-modified time). DSS engine only; incompatible with Spark/SQL engines. Values populated only at run time; design preview shows placeholder text.

## Params Seen In Live Payloads (Primary)

| Param | Required | Domain | Allowed values | Notes |
| --- | --- | --- | --- | --- |
| `partitionOutputColumn` | no | `string<column_name>` | Any valid output column name | Partition column; created only when non-blank; source partition id (partitioned inputs). |
| `filenameOutputColumn` | no | `string<column_name>` | Any valid output column name | Filename column; created only when non-blank; source filename (file-based inputs). |
| `lastModifiedOutputColumn` | no | `string<column_name>` | Any valid output column name | Last-modified column; created only when non-blank; timestamp formatted `yyyy-MM-dd HH:mm:ss` (file-based inputs). |
| `filepathOutputColumn` | no | `string<column_name>` | Any valid output column name | File-path column; created only when non-blank; source file path (file-based inputs). |
| `fileRecordOutputColumn` | no | `string<column_name>` | Any valid output column name | File-record column; created only when non-blank; numeric record id within file (file-based inputs). |
| `partitionChunksOutputColumnsPrefix` | no | `string<any>` | Any column-name prefix | Partition-chunks prefix; created only when non-blank; one column per partition dimension named `<prefix><dimensionName>` (partitioned inputs); variable column count; marks lineage uncertain. |

## Canonical Variant

```json
{
  "type": "EnrichWithRecordContextProcessor",
  "params": {
    "partitionOutputColumn": "src_partition_id",
    "filenameOutputColumn": "src_filename",
    "lastModifiedOutputColumn": "src_last_modified",
    "filepathOutputColumn": "src_filepath",
    "fileRecordOutputColumn": "src_file_record",
    "partitionChunksOutputColumnsPrefix": "src_partdim_"
  }
}
```
