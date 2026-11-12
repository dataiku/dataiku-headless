# Custom LLM Plugin Components

Start with [Plugin development](../plugin-development.md). A custom LLM connection
can provide text completion, image-aware completion, embeddings, or reranking,
depending on its implementation and the provider.

Create `python-llms/<component-id>/llm.json` and `llm.py` locally, following the
[custom LLM tutorial](https://developer.dataiku.com/latest/tutorials/plugins/llm-connection/generality/index.html).
Use the interface for the operation you need:

- For completion, implement `BaseLLM` from `dataiku.llm.python`. Translate messages,
  settings, tool calls, errors, and usage metadata between Dataiku and the provider.
  If you support streaming, return the expected chunks and final metadata.
- For image inputs, preserve each message's text and image parts when adapting the
  request. Handle the image representations the provider accepts and reject
  unsupported inputs clearly. Image understanding and image generation are separate
  capabilities; implementing one does not provide the other.
- For embeddings, implement `BaseEmbeddingModel` and return the vector and supported
  usage metadata. Keep embedding requests separate from chat requests. Test vector
  dimensions, input limits, and any distinction between document and query embeddings.

Advertise only capabilities you implement. Test each supported operation in Dataiku,
including malformed inputs, provider failures, streaming where supported, and whether
embeddings work with the intended retrieval workflow.

## Examples

- [TypeSafe AI](https://github.com/dataiku/dss-plugin-typesafe-ai):
  `python-llms/jev-reranker` implements `BaseRerankingModel`, scoring documents for
  relevance and returning their original indices, relevance scores, and usage metadata.
- The [custom LLM tutorial](https://developer.dataiku.com/latest/tutorials/plugins/llm-connection/generality/index.html)
  shows how to translate image inputs into a provider request.
- The [LLM Mesh examples](https://developer.dataiku.com/latest/concepts-and-examples/llm-mesh.html)
  show how to call embedding models through Dataiku when validating the connection.
