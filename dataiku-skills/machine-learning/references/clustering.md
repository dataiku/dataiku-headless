# Clustering

Clustering groups similar records without a target column. Its value comes from whether the resulting segments are stable, distinguishable, and useful for a decision.

## Design Guidance

Choose features that describe the behavior or attributes to segment. Reject identifiers, row numbers, high-cardinality labels, and unprocessed free text unless there is a clear reason to include them.

Feature scale matters. Large-scale numeric features can dominate distance-based methods, so assess preprocessing and scaling before interpreting clusters.

Choose a cluster count or algorithm based on segment usefulness and stability, not only an internal score. Consider whether clusters have enough members to support an action.

## Evaluation And Interpretation

Inspect cluster sizes, representative feature values, and whether each segment has a meaningful business interpretation.

Outliers can become their own clusters or distort other clusters. Determine whether they represent a meaningful rare segment, data-quality issue, or records to handle separately.

Cluster labels are arbitrary identifiers, not ordered scores. Do not imply that one cluster is inherently better or worse without supporting evidence.

## Red Flags

- A cluster is mostly a unique identifier, location code, or other label.
- One cluster contains almost every record while others are too small to act on.
- Minor preprocessing changes produce very different segments.
- Free text or sparse high-cardinality values dominate similarity.
