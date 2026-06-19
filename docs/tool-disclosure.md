# Tool disclosure — why one code-mode tool, and when BM25 search would matter

Status: **design note.** Records FastMCP's search-based tool-exposure mechanism
as a future option and explains why our current one-tool design sidesteps the
problem it solves. Nothing here changes the MCP server today.

## What we ship

The MCP server exposes exactly **one** tool: `dku_exec`. It runs the `dku` CLI as
the user, in code-mode — the model composes a shell command line and the full
`dku` surface (every noun, verb, flag, enum) is reached *through that one tool*.
The tool's input schema is a command string; the CLI's own `--help` (structured
JSON) is the schema for everything underneath. This is the "code-mode" pattern:
the agent writes code (a command line), the host executes it, capabilities are
discovered at call time via `--help`, not enumerated up front as tool schemas.

## The typed-tool alternative

The opposite MCP shape registers **many typed, async tools** (`@mcp.tool`), one
per operation — `create_recipe`, `get_recipe_settings`, `set_recipe_settings`,
`build_dataset`, and so on, organized by domain. Every tool ships its own
Pydantic-typed input schema; a mid-size DSS surface lands at well over a hundred
such tools.

To manage the resulting catalog size, FastMCP offers an opt-in search-exposure mode:

```bash
DKU_MCP_TOOL_EXPOSURE=search          # default is "full"
DKU_MCP_SEARCH_MAX_RESULTS=5          # matches returned per search
DKU_MCP_SEARCH_ALWAYS_VISIBLE=get_current_instance   # CSV of pinned tools
```

- `full` advertises the entire catalog to the client up front.
- `search` collapses the visible surface to just `search_tools` + `call_tool`
  (plus any pinned `ALWAYS_VISIBLE` tools). The agent calls `search_tools` with a
  natural-language query, a **BM25** ranker (`fastmcp`'s `BM25SearchTransform`)
  returns the top-`N` matching tool schemas, and the agent then invokes the chosen
  tool via `call_tool`. It is progressive disclosure: pay the schema-context tax
  only for the handful of tools you actually ranked into, not the whole catalog.

Search mode exists for exactly this reason — harnesses that struggle with large
tool catalogs or over-consume context on tool schemas.

## The tax search mode is paying down

A typed-tool MCP server pushes every tool's name, description, and full input
schema into the model's context on connect — for a hundred-plus tools that is a large,
fixed, per-session token cost the agent pays before doing any work, every
session, whether or not it touches those tools. It also widens the model's
choice space (more near-duplicate tools to disambiguate → more mis-selection).
BM25 search mode is a direct mitigation: hide the catalog, retrieve on demand.

## Why our one-tool design sidesteps it entirely

`dku_exec` advertises **one** schema. The context cost of "what tools exist" is
flat and tiny regardless of how large the `dku` surface grows — new nouns, verbs,
and flags add zero up-front schema tax because they are not tools, they are CLI
arguments discovered via `--help` only when the agent needs them. So:

- **No catalog-size tax.** We never enumerate 150 schemas; we enumerate one.
- **Built-in progressive disclosure.** `dku --help` → groups, `dku recipe
  --help` → commands, `dku recipe create-join --help` → flag detail. The agent
  pulls exactly the slice it needs, when it needs it — the same goal BM25 search
  chases, achieved by the CLI's own scoped help tree instead of a retrieval layer.
- **One disambiguation surface.** The model picks a command string, not one of
  150 look-alike tools, so tool-selection error drops.
- **Pipe/compose for free.** Code-mode means the agent can chain `dku … | jq …`,
  loop, and filter in one call — impossible when each operation is a separate
  typed tool requiring a round-trip.

The trade we accept: typed tools give the host hard, per-argument validation at
the MCP boundary; code-mode pushes validation into the CLI (`click.Choice` enums,
prescriptive exit-2 errors, exit-77 safety guards). For our tenets — design for
no memory, make the illegal unrepresentable loudly, one fact one home — the CLI
is the better place for that validation anyway, because careful humans hit the
exact same guardrails.

## If we ever add typed tools alongside `dku_exec`

We might, someday, expose a few high-frequency operations as typed tools (for
hosts that can't run a shell, or to get boundary-level validation on a hot path).
If we do, the catalog-size tax comes back the moment that set grows. The lesson
to import then is **not** "register everything typed and hope" — it is the
exposure-mode escape hatch:

1. Keep `dku_exec` as the default, always-visible tool. The CLI remains the full
   surface; typed tools are a convenience layer, never the only path.
2. Pin only a tiny `ALWAYS_VISIBLE` core (instance/auth context).
3. Behind any larger typed set, gate disclosure behind a `search_tools` +
   `call_tool` retrieval mode (BM25 or embedding-ranked) so the per-session schema
   cost stays bounded — exactly the mechanism above.

Until then, one tool plus a self-describing CLI is strictly cheaper on context
and strictly simpler to reason about, and the tool-explosion problem is one we do
not have.
