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
    # --contract payload shape (non-derivable from --help): a per-output map of
    # value expectations, each field asserted only when present.
    ("project", "audit"): [
        "dku project audit -P PROJ",
        "dku project audit -P PROJ --bucket structure --bucket documentation"
        "  # run a subset; skipping evidence avoids the flow check + metric reads",
        "dku project audit -P PROJ --contract @contract.json"
        '  # contract.json: {"outputs":{"global_sales_by_region":'
        '{"min_rows":1,"columns":["Region","2023 Total Sales Euro"],'
        '"types":{"2023 Total Sales Euro":"double"},"not_blank":["Region"]}}}',
    ],
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
    ("dataset", "schema"): [
        "dku dataset schema customers -P PROJ --fields name,type,description",
    ],
    # The recurring single-column-upload repair: upload resets formatParams, so
    # re-apply the CSV format via -d @file (payload shape non-derivable from
    # --help; no stdin redirection — '<' is not supported, use -d @file or -d -).
    ("dataset", "set-definition"): [
        "dku dataset set-definition raw_input -d @def.json --deep-merge -P PROJ"
        '  # def.json: {"formatType":"csv","formatParams":{"style":"excel",'
        '"charset":"utf-8","separator":"\\t","quoteChar":"","escapeChar":"\\\\",'
        '"parseHeaderRow":true,"skipRowsBeforeHeader":0}}',
    ],
    # Repeatable -i + required output combination
    ("recipe", "create"): [
        "dku recipe create clean_orders --type prepare -i orders"
        " --output-ds orders_clean -P PROJ",
        # Plugin recipe with multiple roles: repeatable ROLE=DATASET pairs
        "dku recipe create score_all -t CustomCode_myplugin_score"
        " --input-role main=orders --output-role decisions=out_a"
        " --output-role diagnostics=out_b --params '{\"threshold\": 0.5}' -P PROJ",
    ],
    # Repeatable -i; --join-key 'left=right' and 'INDEX:key' prefix for 3+ inputs;
    # inequality operators make range self-joins flags-only (no payload surgery).
    # The self-join detail alias ('1:w_price=...') is required: same-named
    # columns are silently dropped (anchor wins), breaking downstream Groups.
    ("recipe", "create-join"): [
        "dku recipe create-join join_orders -i orders -i customers"
        " --join-key customer_id --output-ds joined -P PROJ",
        "dku recipe create-join join_all -i orders -i customers -i refunds"
        " --join-key customer_id --join-key '1:order_id' --output-ds joined -P PROJ",
        "dku recipe create-join self_roll -i seq_ds -i seq_ds -j INNER"
        " --computed-col '0:win_end=seq + 2:bigint'"
        " --computed-col '1:w_price=price:double'"
        " --join-key 'seq<=seq' --join-key 'win_end>=seq' --output-ds rolled -P PROJ",
    ],
    # A distance-threshold predicate is INNER, and same-named columns collide
    # (one copy kept) — rename one side and match left=right to keep both.
    ("recipe", "create-fuzzy-join"): [
        "dku recipe create-fuzzy-join fuzzy_names -i left -i right"
        " --fuzzy-key name --output-ds matched --max-distance 2 -P PROJ",
        "dku recipe create-fuzzy-join fuzzy_names -i left -i right_renamed"
        " --fuzzy-key name=name_r --max-distance 2 --join-type INNER"
        " --output-ds matched -P PROJ",
    ],
    # Required flag combination: input + output + connection + sql
    ("recipe", "create-sql"): [
        "dku recipe create-sql sql_orders -i orders --output-ds joined"
        " --connection pg_conn --sql 'SELECT * FROM orders' -P PROJ",
    ],
    ("recipe", "create-llm-eval"): [
        "dku recipe create-llm-eval review_evaluate --input review_answers"
        " --eval-store REVIEW_ES --task-type QUESTION_ANSWERING"
        " --metrics bertScore --input-col question --output-col llm_output"
        " --ground-truth-col reference_answer -P PROJ",
    ],
    ("recipe", "create-embed"): [
        "dku recipe create-embed embed_products --input products"
        " --output-kb products_kb --embedding-llm EMBED_LLM"
        " --embed-column description --metadata-col product_id"
        " --metadata-col url -P PROJ",
    ],
    # One artifact for a whole prepare pipeline: op DSL + raw {type,params}
    # escape in one array, validated as a batch before any save. Replaces N
    # add-* calls (each with its own --help). --replace for idempotent rebuilds.
    ("recipe", "apply-spec"): [
        "dku recipe apply-spec clean @steps.json -P PROJ"
        '  # steps.json: [{"op":"formula","column":"total","expr":"price*qty"},'
        '{"op":"rename","mappings":{"old":"new"}},'
        '{"op":"delete-columns","columns":["tmp","scratch"]},'
        '{"type":"DateParser","params":{"appliesTo":"SINGLE_COLUMN",'
        '"columns":["d"],"outCol":"d2","outType":{"name":"out","type":"date"}}}]',
        "dku recipe apply-spec clean @steps.json --replace -P PROJ",
    ],
    # @file convention (--code takes literal, @file.py, or '-')
    ("recipe", "set-code"): [
        "dku recipe set-code compute_joined --code @script.py -P PROJ",
    ],
    ("recipe", "run"): [
        "dku recipe run clean_orders -P PROJ --type RECURSIVE_BUILD --wait",
    ],
    # --payload (not --definition) for visual config; --deep-merge to patch nested keys
    ("recipe", "set-definition"): [
        "dku recipe set-definition join_orders --payload"
        ' \'{"postFilter": {"enabled": true}}\' --deep-merge -P PROJ',
        "dku recipe set-definition py_recipe -d"
        ' \'{"params":{"containerSelection":{"containerMode":"NONE"}}}\''
        " --deep-merge -P PROJ"
        "  # omitting the merge flag drops sibling params keys",
    ],
    ("job", "run"): [
        "dku job run --target joined -P PROJ --type RECURSIVE_BUILD --wait",
        "dku job run --target joined --target joined_metrics -P PROJ"
        " --type RECURSIVE_BUILD --wait",
    ],
    # Repeatable --tool + @file system prompt; one-call tool-calling loop graph
    ("agent", "create-react"): [
        "dku agent create-react researcher --llm openai:conn:gpt-4o"
        " --tool web_search --tool kb_search --system-prompt @sys.txt -P PROJ",
    ],
    # Type-conditional required flag (VectorStoreSearch needs --kb)
    ("agent-tool", "create"): [
        "dku agent-tool create search_kb --type VectorStoreSearch --kb kb_id -P PROJ",
    ],
    # Input payload shape: logical input at the root, no {"input": ...} envelope
    ("agent-tool", "run"): [
        "dku agent-tool run lookup_tool --input "
        '\'{"filter": {"column": "sku", "operator": "EQUALS", '
        '"value": "ABC-123"}}\' -P PROJ',
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
    # Params payload shape; --print-result fetches the rendered output (implies --wait)
    ("macro", "run"): [
        'dku macro run MACRO_ID --params \'{"param1": "value"}\' --wait -P PROJ',
        'dku macro run MACRO_ID --params \'{"param1": "value"}\' --print-result -P PROJ',
    ],
    # --step targets one custom_python step's script on a step-based scenario
    ("scenario", "set-code"): [
        "dku scenario set-code SCEN_ID --step 2 --code @step.py -P PROJ",
    ],
    # rule-schema emits a template consumed via --config @file
    ("dq", "create"): [
        "dku dq create customers --config @rule.json -P PROJ"
        "  # rule.json from: dku dq rule-schema ValuesInSetRule",
    ],
    # Plugin webapp instantiation: --from-plugin/--component pair, JSON --config
    ("webapp", "create"): [
        "dku webapp create MyApp --from-plugin traces-explorer"
        ' --component traces-explorer --config \'{"k":"v"}\' -P PROJ',
    ],
    # Dotted-path projection over the raw settings blob
    ("project", "get-settings"): [
        "dku project get-settings PROJ --fields codeEnvs.python.mode,containerSelection",
    ],
    # Repeatable --spec / --check / --item
    ("project-standards", "create-checks"): [
        "dku project-standards create-checks --spec projectmusthaveadescription"
        " --spec projectmusthavetags",
    ],
    ("project-standards", "create-scope"): [
        "dku project-standards create-scope --name ml-scope"
        " --check Projectmusthaveadescription --selection-method BY_PROJECT"
        " --item PROJ1 --item PROJ2",
    ],
    # Check-param schema and @file convention
    ("project-standards", "update-check"): [
        "dku project-standards update-check CHECK_ID --params @params.json",
    ],
    # Explicit runs are diagnostic and do not replace the saved scoped report
    ("project-standards", "run"): [
        "dku project-standards run --check CHECK_A --check CHECK_B -P PROJ",
    ],
    # Repeatable KEY=VALUE
    ("config", "set-variables"): [
        "dku config set-variables --set env=prod --set region=eu-west-1",
    ],
    # KEY=VALUE assignments — geo meaning is the primary use case (charts fail
    # to render without it), but the pattern works for any meaning.
    ("dataset", "set-meaning"): [
        "dku dataset set-meaning sales geopoint=GeoPoint -P PROJ",
        "dku dataset set-meaning sales latitude=Latitude longitude=Longitude -P PROJ",
    ],
    ("knowledge", "search"): [
        'dku knowledge search products_kb --query "specific product details"'
        " --max 5 -P PROJ",
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
    ("govern", "signoff", "update-status"): [
        "dku govern signoff update-status ar.5 exploration NOT_STARTED --reload",
    ],
    ("govern", "signoff", "delegate-feedback"): [
        "dku govern signoff delegate-feedback ar.5 exploration --group-id reviewers"
        ' --users-container \'{"type":"user","login":"alice"}\'',
        "dku govern signoff delegate-feedback ar.5 exploration --group-id reviewers"
        ' --users-container \'{"type":"globalApiKey","globalAPIKeyId":"gk_123"}\'',
    ],
    ("govern", "signoff", "delegate-approval"): [
        "dku govern signoff delegate-approval ar.5 exploration"
        ' --users-container \'{"type":"user","login":"alice"}\'',
        "dku govern signoff delegate-approval ar.5 exploration"
        ' --users-container \'{"type":"globalApiKey","globalAPIKeyId":"gk_123"}\'',
    ],
    # Datapoint payload shape: epoch-ms timestamps
    ("govern", "time-series", "push-values"): [
        "dku govern time-series push-values TS_ID --datapoints"
        ' \'[{"timestamp": 1718000000000, "value": 42}]\'',
    ],
    # Repeatable --model flag; method must match the problem type
    ("ml", "ensemble"): [
        "dku ml ensemble a1 t1 --model MID1 --model MID2"
        " --method PROBA_AVERAGE -P PROJ  # classification",
        "dku ml ensemble a1 t1 --model MID1 --model MID2"
        " --method AVERAGE -P PROJ  # regression",
    ],
}


def examples_for(path: list[str]) -> list[str]:
    return EXAMPLES.get(tuple(path), [])
