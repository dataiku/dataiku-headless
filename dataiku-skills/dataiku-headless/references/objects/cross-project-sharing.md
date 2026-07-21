# Cross-project sharing

Sharing is outbound: a source project owns an object and exposes it to one or
more target projects. The target consumes the shared object read-only; ownership
and lifecycle stay with the source.

Use `list_shared_objects` on the source project. Read each object's type,
`local_name`, and `target_projects`; this does not list objects shared *into*
the source. Catalog membership does not create this relationship.

Before requesting a change, identify the source project, target projects, and
exact object. Inspecting the source sharing configuration requires Read Project
Content and Write Project Content permissions on that source project.
