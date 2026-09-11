# Govern artifacts

Use the connected `client` from [Govern](../govern.md). Variables such as
`blueprint_id`, `version_id`, and `artifact_id` below come from discovery or the user.

## Discover and inspect

```python
blueprints = [item.get_raw() for item in client.list_blueprints()]
blueprint = client.get_blueprint(blueprint_id)
versions = [item.get_raw() for item in blueprint.list_versions()]
version = blueprint.get_version(version_id)
schema = version.get_definition().get_raw()
field_definitions = schema["fieldDefinitions"]
```

Search with the SDK's query objects. Keep the same request across pages; fetching
only the first page is not a complete inventory. Stop early when the task only
needs a sample, and report that limit.

```python
from dataikuapi.govern.artifact_search import (
    GovernArtifactFilterBlueprints, GovernArtifactSearchQuery,
)

query = GovernArtifactSearchQuery(
    artifact_filters=[GovernArtifactFilterBlueprints([blueprint_id])]
)
request = client.new_artifact_search_request(query)
while True:
    hits = request.fetch_next_batch().get_response_hits()
    if not hits:
        break
    for hit in hits:
        record = hit.get_raw()["artifact"]
        print({"id": record["id"], "name": record.get("name")})
```

For an existing artifact, inspect its own blueprint version; another version of
the same blueprint can have different fields.

```python
artifact = client.get_artifact(artifact_id)
definition = artifact.get_definition()
raw = definition.get_raw()
schema = definition.get_blueprint_version().get_definition().get_raw()
```

## Create or update

For creation, select an ACTIVE version and inspect its fields before assembling
`field_values`. Retain the returned ID and re-read the created artifact.

```python
artifact = client.create_artifact({
    "blueprintVersionId": {"blueprintId": blueprint_id, "versionId": version_id},
    "name": artifact_name,
    "fields": field_values,
})
created = artifact.get_definition().get_raw()
```

For an update, `get_raw()` returns a mutable definition. Preserve the other fields,
blueprint reference, and workflow; a partial replacement can lose unrelated state.

```python
definition = artifact.get_definition()
definition.get_raw().setdefault("fields", {}).update(field_updates)
definition.save()
saved = artifact.get_definition().get_raw()
for field_id, expected in field_updates.items():
    if saved.get("fields", {}).get(field_id) != expected:
        raise RuntimeError(f"Field did not persist as requested: {field_id}")
```

## Field rules

- Fields are keyed by ID in `fieldDefinitions`; the type key is `fieldType`.
  Use the actual field ID, not its display label. User-entered values belong in
  `sourceType: STORE` fields; preserve computed fields.
- `listConfig` makes a field a list, even if the configuration is empty. Send an
  array for one value as well. CATEGORY values must match the defined categories.
- REFERENCE values are artifact IDs, including references to user/group artifacts;
  they are not logins or group names. Inspect `allowedBlueprints` before selecting them.
- DATE values use an ISO-8601 datetime with timezone. Uploaded files and time series
  use IDs from their own API operations; see [Supporting objects](./supporting-objects.md).

For workflow transitions or approvals, follow [Signoffs](./signoffs.md). An artifact
field edit is not a substitute for submitting feedback or approval.
