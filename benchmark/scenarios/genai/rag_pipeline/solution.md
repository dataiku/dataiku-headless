# Solution

Executable baseline for the current CLI and harness.

## Not Yet Validated By Harness

- The benchmark intent is a usable retrieval-grounded RAG setup, not just object creation.
- The current executable path proves KB creation and RAG object creation only.

```bash
dku recipe create-embed embed_products_for_rag --input products --output-kb products_kb --embedding-llm "$(dku llm list --purpose TEXT_EMBEDDING_EXTRACTION -P {project} -o json | jq -r '.[0].id')" --embed-column category -P {project}
dku knowledge list -P {project} -o json | jq -r '.[] | select(.name=="products_kb") | .id' > /tmp/{project}_kb_id.txt
dku rag create "Products RAG" --kb "$(cat /tmp/{project}_kb_id.txt)" --llm "$(dku llm list -P {project} -o json | jq -r '.[0].id')" -P {project}
dku rag list -P {project} -o json | jq -r '.[0].id' > /tmp/{project}_rag_id.txt
```
