# Test Results

Validation date: 2026-07-28

Module version: 19.0.1.0.0

## Runtime environment

- Official Odoo container: Odoo 19.0-20260630
- PostgreSQL container: PostgreSQL 16.14
- Fresh test database: `codex_project_approval_test4`
- Test tag: `/project_task_approval_matrix`
- Demo data: disabled

The supplied source repository did not contain an Odoo Enterprise runtime.
Runtime validation therefore used the official Odoo 19 container and only the
module's declared standard dependencies. The module uses APIs and views shared
by Odoo 19 Enterprise.

## Results

| Check | Result | Evidence |
|---|---|---|
| Clean module install | PASS | Container exited 0; registry loaded successfully |
| Focused automated suite | PASS | `0 failed, 0 error(s) of 23 tests` |
| Odoo module test statistics | PASS | `project_task_approval_matrix: 37 tests`, 17.69 seconds, 7,480 queries |
| Module upgrade | PASS | Container exited 0; module reloaded and registry verified |
| Module uninstall | PASS | Container exited 0; final state `uninstalled` |
| Python compilation | PASS | All production, migration, and test Python files compiled |
| XML validation | PASS | 8 XML files parsed successfully |
| Access CSV validation | PASS | Header and 4 access rows validated |
| Odoo XML IDs and inherited views | PASS | Resolved during clean install and upgrade |
| Deprecated `attrs`/`states` syntax | PASS | None found |
| Placeholder/incomplete Python code | PASS | No TODO, FIXME, `NotImplementedError`, or placeholder `pass` found |

## Automated coverage

The included tests cover:

- Projects with the matrix disabled and enabled
- Normal tasks and subtasks, including tasks that do not require approval
- Sequential and parallel activation, partial approval, and final approval
- Assigned-approver enforcement and self-approval prevention
- Rejection, request changes, resubmission, reset, and controlled manager override
- Exact approval-activity linkage and stale-activity cleanup
- Closing-stage and Odoo task-state completion blocking through ORM writes
- Project, task, and subtask duplication without duplicate task creation
- Approval-route preservation with all decisions and activities reset
- Hours and days conversion using task, employee, company, and 8-hour fallback calendars
- Import/API synchronization with standard `allocated_hours`
- Portal access denial and multi-company separation

## Log review

No warning, error, critical message, or traceback was emitted by
`project_task_approval_matrix`.

The clean database log contained one standard container configuration warning
about the future default HTTP interface and two docutils parser notices while
Odoo's core `mail` module was loading. These occurred before the custom module
loaded and are not produced by this module.

## Source compatibility checks

- Confirmed `project.task.allocated_hours` in Odoo 19 source.
- Confirmed task form `project.view_task_form2`.
- Confirmed project form `project.edit_project`.
- Confirmed task search view `project.view_task_search_form`.
- Confirmed task-stage views `project.task_type_edit` and
  `project.task_type_tree`.
- Confirmed standard project duplication uses the Odoo task-mapping flow; this
  module extends standard copy behavior and does not create a second task loop.
