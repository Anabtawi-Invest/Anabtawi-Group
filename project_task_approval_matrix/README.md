# Project Task Approval Matrix

`project_task_approval_matrix` is an Odoo 19 add-on that adds optional,
project-scoped approvals to tasks and subtasks while preserving the standard
Project workflow for projects that do not opt in.

## Highlights

- Per-project feature switch and completion policy
- Per-task and per-subtask approval requirement
- Sequential and parallel approval routes
- Exact-line Odoo activities and internal chatter audit notes
- Rejection, change request, reset, and controlled manager override
- Approval-closing task stages with server-side enforcement
- Hours or days allocation synchronized with standard `allocated_hours`
- Calendar priority: task, main assigned employee, company, then 8 hours
- Standard Odoo project/task duplication hooks with decision reset
- Internal-user, manager, portal, and multi-company security controls
- Optional queued email notifications

## Compatibility

- Odoo 19.0 Enterprise or Community
- Required Odoo modules: `project`, `mail`, `hr`, and `resource`
- `hr_timesheet` remains compatible but is not forced as a dependency because
  Odoo 19 defines `project.task.allocated_hours` in the core Project module.

See [INSTALLATION.md](INSTALLATION.md), [USER_GUIDE.md](USER_GUIDE.md), and
[TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md) for deployment and
operation details.
