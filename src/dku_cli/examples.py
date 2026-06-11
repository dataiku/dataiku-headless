"""Copy-pasteable command examples for agent help.

Explicit registry (no docstring scraping), rendered in the spec JSON at
command-level help. Curation rule: an example earns its place only when it
encodes invocation shape the flag spec alone cannot teach — JSON payload
shapes, repeatable flags, required flag combinations, @file/stdin conventions,
KEY=VALUE or prefixed syntaxes. No synopsis echoes: a command whose only
reasonable invocation is `<command> <arg>` gets no example.

Stable placeholders: ``PROJ``, ``customers``, ``orders``, ``joined``.
Global flags (``--format``) go before the noun.
"""

from __future__ import annotations

EXAMPLES: dict[tuple[str, ...], list[str]] = {
    # Global --format placement (before the noun) — taught once, here.
    ("dataset", "list"): [
        "dku --format json dataset list -P PROJ",
        "dku --format ids dataset list -P PROJ",
    ],
    # Type + connection pairing
    ("dataset", "create"): [
        "dku dataset create customers --type PostgreSQL -c pg_conn -P PROJ",
    ],
    # Local file-path argument
    ("dataset", "create-from-file"): [
        "dku dataset create-from-file customers ./customers.csv -P PROJ",
    ],
    # Repeatable -i + required output combination
    ("recipe", "create"): [
        "dku recipe create compute_joined --type python -i orders -i customers"
        " --output-ds joined -P PROJ",
    ],
    # Repeatable -i; --join-key 'left=right' and 'INDEX:key' prefix for 3+ inputs
    ("recipe", "create-join"): [
        "dku recipe create-join join_orders -i orders -i customers"
        " --join-key customer_id --output-ds joined -P PROJ",
        "dku recipe create-join join_all -i orders -i customers -i refunds"
        " --join-key customer_id --join-key '1:order_id' --output-ds joined -P PROJ",
    ],
    # Required flag combination: input + output + connection + sql
    ("recipe", "create-sql"): [
        "dku recipe create-sql sql_orders -i orders --output-ds joined"
        " --connection pg_conn --sql 'SELECT * FROM orders' -P PROJ",
    ],
    # @file convention (--code takes literal, @file.py, or '-')
    ("recipe", "set-code"): [
        "dku recipe set-code compute_joined --code @script.py -P PROJ",
    ],
    # --payload (not --definition) for visual config; --deep-merge to patch nested keys
    ("recipe", "set-definition"): [
        "dku recipe set-definition join_orders --payload"
        ' \'{"postFilter": {"enabled": true}}\' --deep-merge -P PROJ',
    ],
    # Type-conditional required flag (VectorStoreSearch needs --kb)
    ("agent-tool", "create"): [
        "dku agent-tool create search_kb --type VectorStoreSearch --kb kb_id -P PROJ",
    ],
    # Input payload shape: logical input at the root, no {"input": ...} envelope
    ("agent-tool", "run"): [
        'dku agent-tool run tool_id --input \'{"query": "refund policy"}\' -P PROJ',
    ],
    # Paired question/expected-answer flags
    ("agent-review", "create-test"): [
        "dku agent-review create-test review_id -q 'What is the refund policy?'"
        " -r 'Refunds within 30 days.' -P PROJ",
    ],
    # Inline JSON schema or @file for structured output
    ("llm", "completion"): [
        "dku llm completion LLM_ID 'Extract the entities' --json-schema @schema.json"
        " -P PROJ",
    ],
    # Repeatable --doc
    ("llm", "rerank"): [
        "dku llm rerank RERANK_LLM_ID -q 'best restaurant' --doc 'Pizza place'"
        " --doc 'Sushi bar' -P PROJ",
    ],
    # Repeatable -v, destructive so --yes
    ("model", "delete-version"): [
        "dku model delete-version MODEL_ID -v v1 -v v2 --yes -P PROJ",
    ],
    # Params payload shape
    ("macro", "run"): [
        'dku macro run MACRO_ID --params \'{"param1": "value"}\' --wait -P PROJ',
    ],
    # Repeatable KEY=VALUE
    ("config", "set-variables"): [
        "dku config set-variables --set env=prod --set region=eu-west-1",
    ],
    # Ergonomic mode: -f KEY=VALUE (JSON arrays for list fields) vs raw --definition
    ("govern", "artifact", "create"): [
        "dku govern artifact create -b bp.system.govern_project -n 'Customer Analytics'"
        " -f description='Quarterly review' -f 'tags=[\"pii\",\"finance\"]'",
        "dku govern artifact create --definition @artifact.json",
    ],
    # KEY=VALUE field filter; --all for reliable counts
    ("govern", "artifact", "list"): [
        "dku govern artifact list -b bp.system.govern_project"
        " --field sensitive_data=Yes --all",
    ],
    # Datapoint payload shape: epoch-ms timestamps
    ("govern", "time-series", "push-values"): [
        "dku govern time-series push-values TS_ID --datapoints"
        ' \'[{"timestamp": 1718000000000, "value": 42}]\'',
    ],
}


def examples_for(path: list[str]) -> list[str]:
    return EXAMPLES.get(tuple(path), [])
