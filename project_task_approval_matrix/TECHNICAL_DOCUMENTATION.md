# Technical Documentation

## Verified Odoo 19 extension points

The implementation was checked against the official Odoo 19.0 source:

- Standard allocation field: `project.task.allocated_hours`
- Project form: `project.edit_project`
- Task form: `project.view_task_form2`
- Task search form: `project.view_task_search_form`
- Task stage forms: `project.task_type_edit` and `project.task_type_tree`
- Project duplication: `project.project.copy()` calls `map_tasks()`
- Task/subtask duplication: `project.task.copy_data()` recursively prepares
  child commands and standard dependency mapping

The add-on does not copy project tasks itself. Its copied task fields and
approval-line One2many data flow through those standard hooks, preventing a
second task-copy loop.

## Models

### `project.project`

Stores the feature switch, completion policy, self-approval policy, and email
policy. Approval settings are copied with the project. Only Approval Managers
may change them.

### `project.task`

Stores task/subtask configuration and current workflow summary. Decision fields
are protected from direct writes. Workflow actions perform authorization first,
then use private internal transition methods.

`write()` enforces approval-closing stages and standard Done state for form
edits, Kanban changes, imports, RPC, API, automation, and server actions.

### `project.task.approval.line`

Stores one approver per task. Odoo 19 `models.Constraint` definitions enforce a
unique task/approver pair and positive sequence. Configuration edits are locked
during active rounds. Approvers can update comments only on their own pending
line.

### `mail.activity`

`project_task_approval_line_id` links each approval activity to its exact route
line. Cleanup domains include the line, task model, and task ID, so unrelated
task activities are never closed.

### `project.task.type`

`approval_closing_stage` explicitly marks closing stages without relying on a
translated or customized stage name.

## Workflow

Sequential submission sets the first line Pending and later lines Waiting.
Approval closes the exact activity and activates the next line. Parallel
submission sets every line Pending; one approval produces Partially Approved.
All approved lines produce final approval.

One rejection or change request closes every still-open activity in the round,
marks unhandled lines Cancelled, notifies task assignees, and preserves the audit
history in internal chatter.

## Allocation synchronization

`_prepare_allocated_hours()` is reused by create, write, copy-generated create,
import, API writes, and onchange. Custom allocation values are authoritative
when supplied. A direct write to standard `allocated_hours` switches the display
unit to Hours and mirrors the entered value, preventing recursion.

The post-init hook initializes existing tasks as Hours with
`allocation_value == allocated_hours` and does not change standard hours.

## Security

- Global company rule applies `company_ids` isolation.
- Project users can read lines only when assigned, approving, or managing the
  project.
- Approvers see the route for tasks on which they are an approver and can act
  only on their own pending line.
- Managers have route access within the global company rule.
- Portal users receive no approval-line ACL.
- Internal workflow sudo is limited to exact, already-authorized route lines and
  linked activities so one approver can close stale technical records without
  gaining general access.

Audit chatter uses the internal-note subtype to avoid publishing approval details
to portal followers.

## Email

Email is disabled per project by default. When enabled, templates queue mail for
pending steps, negative decisions, and final completion. Version 1 does not
support approval through public email links.
