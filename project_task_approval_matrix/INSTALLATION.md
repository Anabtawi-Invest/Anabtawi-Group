# Installation

## Prerequisites

- Odoo 19.0 with `project`, `mail`, `hr`, and `resource`
- A database backup before installing into an existing environment
- An add-ons path writable by the deployment account

## Install

1. Copy the `project_task_approval_matrix` directory into a configured custom
   add-ons path.
2. Restart all Odoo application workers.
3. Update the Apps list.
4. Install **Project Task Approval Matrix**.
5. Assign the Task Approval privilege:
   - **User** reads approval status.
   - **Approver** acts only on their own pending step.
   - **Manager** configures routes, resets workflows, and controls overrides.
6. Under **Project > Configuration > Task Stages**, mark every stage that
   represents task completion as **Approval Closing Stage**.
7. Open a project, select **Settings**, and enable **Use Task Approval Matrix**.

## Command-line install

```bash
odoo-bin -d DATABASE \
  --addons-path=/path/to/odoo/addons,/path/to/custom/addons \
  -i project_task_approval_matrix \
  --stop-after-init
```

## Upgrade

```bash
odoo-bin -d DATABASE \
  --addons-path=/path/to/odoo/addons,/path/to/custom/addons \
  -u project_task_approval_matrix \
  --stop-after-init
```

## Automated tests

```bash
odoo-bin -d TEST_DATABASE \
  --addons-path=/path/to/odoo/addons,/path/to/custom/addons \
  -i project_task_approval_matrix \
  --test-enable \
  --stop-after-init
```

Review the log for `ERROR`, `CRITICAL`, tracebacks, failed tests, unresolved
external IDs, and invalid view inheritance.

## Uninstall

Uninstalling removes only fields, approval lines, templates, activities linked
to approval lines, views, and security records owned by this add-on. It does
not delete projects, tasks, subtasks, timesheets, or standard allocated hours.
Take a backup first and validate uninstall in staging.
