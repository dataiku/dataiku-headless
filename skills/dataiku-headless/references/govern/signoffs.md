# Govern workflow and signoffs

Use the `govern` tool described in [Govern](../govern.md). A blueprint version's
signoff configuration defines a review gate. An artifact's signoff is the runtime
review, including feedback and approval. Inspect both before changing either.

## Workflow state

Read `get_artifact` and its blueprint version. On Govern 13.5+, use
`workflow.steps[step_id]` for state and visibility; order comes from the version's
`workflowDefinition.stepDefinitions`. `status.stepId` is deprecated and may name a
step that is not actually ongoing. See the
[official workflow reference](https://developer.dataiku.com/latest/concepts-and-examples/govern/govern-artifacts/govern-artifact-workflow.html).

When asked to advance the workflow, read the current steps and required signoffs,
change only the intended step states in the full definition, save with
`update_artifact`, and re-read. Preserve visibility and unrelated steps. Do not skip
a required review or rewrite the legacy status field to make signoff creation succeed.

## Configure a review gate

- `list_signoff_configurations` with `blueprint_id` and `version_id` lists gates.
- `get_signoff_configuration` with `step_id` returns one.
- `create_signoff_configuration` with `step_id` and a `configuration` without a
  top-level `id`; the server derives it from the step and version.
- `update_signoff_configuration` replaces the complete `configuration`.
- `delete_signoff_configuration` removes the gate.

Configuration keys:

- `title`, `mandatory`, `feedbackUsersGroups`, `approvers`, and
  `recurrenceConfiguration`. Preserve unrelated settings when updating.
- Each feedback group has an `id`, a non-empty `title`, and a `users` list. The
  group's ID is used by `add_signoff_feedback` and `delegate_signoff_feedback`;
  it is not necessarily a Govern role ID.
- Reviewers and approvers are `{"usersContainer": {...}}` entries. The container
  type is lowercase: `user` (`login`), `group` (`groupName`), `role` (`roleId`),
  or `global-api-key` (`keyId`). Discover the user, group, or role first.
  Approvers form a flat list.
- `recurrenceConfiguration` is `{activated, days, weeks, months, years, reloadConf}`;
  activation needs a positive interval.

Example:

```json
{"title": "Review gate", "mandatory": true,
 "feedbackUsersGroups": [{"id": "reviewers", "title": "Reviewers",
   "users": [{"usersContainer": {"type": "user", "login": "alice"}}]}],
 "approvers": [{"usersContainer": {"type": "user", "login": "bob"}}],
 "recurrenceConfiguration": {"activated": false, "days": 0, "weeks": 0, "months": 0, "years": 0, "reloadConf": false}}
```

Re-read the configuration and check reviewers, approvers, `mandatory`, and the step.
Existing runtime signoffs keep their previous configuration until reset; a
configuration edit alone does not update every review.

## Run a signoff

- `list_signoffs` with `artifact_id` lists the runtime signoffs.
- `get_signoff` returns status, feedback responses, and the approver response.
- `get_signoff_details` resolves reviewer and approver membership to users.
- `create_signoff` creates the review for a step, only when the step is ONGOING and
  a configuration exists. Signoffs may already exist from artifact creation.

| Intent | Operation |
| --- | --- |
| Start feedback or approval collection | `update_signoff_status` with `status: WAITING_FOR_FEEDBACK` or `WAITING_FOR_APPROVAL` and `users_to_notify: []` |
| Read feedback | `list_signoff_feedbacks`, `get_signoff_feedback` |
| Record requested feedback | `add_signoff_feedback` with `group_id`, `status`, `comment` |
| Change or remove a feedback | `update_signoff_feedback`, `delete_signoff_feedback` |
| Read approval | `get_signoff_approval` |
| Record requested approval decision | `add_signoff_approval` with `status`, `comment` |
| Change or remove the approval | `update_signoff_approval`, `delete_signoff_approval` |
| Delegate reviewers | `delegate_signoff_feedback` with `group_id` and `users_container`, or `delegate_signoff_approval` with `users_container` |
| Scheduled reset | `get_signoff_recurrence`, `update_signoff_recurrence` |

Feedback statuses are `APPROVED`, `MINOR_ISSUE`, and `MAJOR_ISSUE`; approval statuses
are `APPROVED`, `REJECTED`, and `ABANDONED`. Signoff statuses move
`NOT_STARTED → WAITING_FOR_FEEDBACK → WAITING_FOR_APPROVAL → APPROVED | REJECTED | ABANDONED`.
Submit decisions only when requested, under the authenticated identity.
Administrative API access does not make that identity a reviewer or approver; check
the configured membership, and do not alter it to bypass a permission error.
Delegation changes who reviews and is not impersonation.

Omitting `users_to_notify` from `update_signoff_status` notifies every configured
reviewer or approver of the target stage. Pass `[]` unless the task authorizes
notifications; when notifying, list `{userLogin, groupId}` entries for the feedback
stage and `{userLogin}` entries for the approval stage. Resetting an in-progress
review requires `ABANDONED` before `NOT_STARTED`; setting `APPROVED` through
`update_signoff_status` is not a substitute for recording an approval.
`reload_conf_for_reset: true` also clears delegations; do not set it incidentally.
