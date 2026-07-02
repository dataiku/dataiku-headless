# Reference: File Bridge

When `dku` runs as a local MCP (stdio), `dku_exec` executes in the user's project
directory with full filesystem access, so the agent can move data between the
user's machine and DSS. Reference relative paths (`./data.csv`) or absolute
paths (`~/Downloads/x.parquet`).

## Local file → DSS dataset

One step — create an UploadedFiles dataset, upload the file, auto-detect schema:

    dku dataset create-from-file <name> <local.csv> -P <PROJECT>
    dku dataset create-from-file sales ./data/sales.csv -P MYPROJ
    dku dataset create-from-file sales ./data/sales.csv -P MYPROJ --overwrite -y

- Auto-detects format + schema. A CSV often detects **every column as STRING** —
  heed the warning and fix numeric columns with `dku dataset set-schema` before
  any group/window recipe, or numeric aggregation fails.
- `--overwrite` wipes + replaces an existing dataset (tier-2 guard → add `-y`).
- To add a file to an EXISTING UploadedFiles dataset:
  `dku dataset upload <name> <local>`.

## DSS dataset → local file

    dku dataset download <name> -P <PROJECT> [out.csv] [--limit N]
    dku dataset download customers ./customers.csv -P MYPROJ --limit 1000

- Streams rows to a CSV file, or to **stdout** if no path is given (pipe into
  `jq`/`python3`/`head`).
- `--limit N` grabs a sample of a large dataset.

## Local files ↔ managed folder (any file type)

    dku folder upload <folder> <local-file> [--path /remote/path]
    dku folder upload-dir <folder> <local-dir>
    dku folder download <folder> <remote-path> [local]

## Typical local loop

1. `dku dataset create-from-file raw ./input.csv -P P` — load a CSV.
2. Build on it (`dku recipe create …`, `dku job build …`, verify).
3. `dku dataset download result ./out.csv -P P` — pull the result back to
   inspect or chart locally.
