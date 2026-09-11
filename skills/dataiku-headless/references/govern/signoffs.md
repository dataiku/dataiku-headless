# Govern workflow and signoffs

Use the connected `client` from [Govern](../govern.md). A blueprint version's
signoff configuration defines a review gate. An artifact's signoff is the runtime
review, including feedback and approval. Inspect both before changing either.

## Workflow state

Read `artifact.get_definition().get_raw()` and its blueprint version. On Govern
13.5+, use `workflow.steps[step_id]` for state and visibility; order comes from
the version's `workflowDefinition.stepDefinitions`. `status.stepId` is deprecated
and may identify a step that is not actually ongoing. See the
[official workflow reference](https://developer.dataiku.com/latest/concepts-and-examples/govern/govern-artifacts/govern-artifact-workflow.html).

When asked to advance workflow, read the current steps and required signoffs,
modify only the intended step states in the full artifact definition, save, and
re-read. Preserve visibility and unrelated steps. Do not skip a required review
or rewrite the legacy status field to make signoff creation succeed.

## Configure a review gate

Get the administrative version through
`client.get_blueprint_designer().get_blueprint(blueprint_id).get_version(version_id)`.
Use its `list_signoff_configurations()` to discover existing gates and
`get_signoff_configuration(step_id).get_definition()` to inspect one.

For an existing configuration, edit its `get_raw()` dictionary and call `save()`.
For a new configuration, call
`version.create_signoff_configuration(step_id, configuration)` without a top-level
`id`; the server derives it from the step and version.

Important payload keys:

- `title`, `mandatory`, `feedbackUsersGroups`, `approvers`, and
  `recurrenceConfiguration`. Preserve unrelated settings when updating.
- Each feedback group has an `id`, `title`, and `users` list. The group's ID is
  used by runtime feedback calls; it is not necessarily a Govern role ID.
- Reviewers and approvers contain `usersContainer`. Prefer the SDK's
  `dataikuapi.govern.users_container` builders, or reuse an inspected container
  shape. Discover the user, group, or role first. Approvers form a flat list.
- Activated recurrence needs a positive interval. Reloading a runtime signoff
  configuration on reset can also clear delegations; do not do it incidentally.

Re-fetch the configuration and check reviewers, approvers, mandatory status, and
the workflow step reference. Existing runtime signoffs may retain their previous
configuration until reset; a configuration edit alone does not update every review.

## Run a signoff

```python
artifact = client.get_artifact(artifact_id)
signoffs = [item.get_raw() for item in artifact.list_signoffs()]
signoff = artifact.get_signoff(step_id)
runtime = signoff.get_definition().get_raw()
details = signoff.get_details().get_raw()
```

Signoffs may already have been created with the artifact. If the required signoff
is absent, create it with `artifact.create_signoff(step_id)` only when its step is
ONGOING and a configuration exists. Creating a handle with `get_signoff()` does
not create a review on the server.

| Intent | Public SDK call on `signoff` |
| --- | --- |
| Start feedback or approval collection | `update_status("WAITING_FOR_FEEDBACK", users_to_notify=[])` or `update_status("WAITING_FOR_APPROVAL", users_to_notify=[])` |
| Read feedback | `list_feedbacks()`; `get_feedback(feedback_id).get_definition().get_raw()` |
| Record requested feedback | `add_feedback(group_id, feedback_status, comment=comment)` |
| Read approval | `get_approval().get_definition().get_raw()` |
| Record requested approval decision | `add_approval(approval_status, comment=comment)` |
| Delegate reviewers | `delegate_feedback(group_id, users_container)` or `delegate_approval(users_container)` |

Feedback statuses are `APPROVED`, `MINOR_ISSUE`, and `MAJOR_ISSUE`; approval statuses
are `APPROVED`, `REJECTED`, and `ABANDONED`. Submit decisions only when requested,
using the authenticated identity. Administrative API access does not make that
identity a reviewer or approver; check the configured membership, and do not alter
it to bypass a permission error. Delegation changes who reviews and is not impersonation.

Omitting `users_to_notify` from `update_status` notifies all configured reviewers
for the target stage. Pass an empty list unless the task authorizes notifications;
when notifying, use the documented recipients for that stage. Re-read
`get_definition()` for status and recorded decisions; `get_details()` resolves
reviewer membership. Resetting an in-progress review requires ABANDONED before
NOT_STARTED; changing status to APPROVED is not a substitute for recording approval.
