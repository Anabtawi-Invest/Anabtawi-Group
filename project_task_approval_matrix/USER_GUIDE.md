# User Guide

## Enable approvals for a project

Open a project and go to **Settings > Task Approval Matrix**.

- **Use Task Approval Matrix** exposes approvals on that project's tasks.
- **Block Task Completion Before Approval** prevents controlled tasks from
  entering approval-closing stages or the standard Done state.
- **Prevent Task Assignee Self-Approval** rejects routes containing an assignee.
- **Send Approval Email Notifications** queues email in addition to activities
  and chatter notifications.

Projects with the feature disabled retain standard Odoo behavior.

## Configure a task or subtask

In the task's **Approvals** tab, an Approval Manager:

1. Enables **Requires Approval**.
2. Selects **Sequential** or **Parallel**.
3. Adds each approver, sequence, and optional approval role.

Routes can be changed only in Draft, Changes Requested, or Rejected status.
Approvers must be active internal users allowed in the task company. Sequential
routes require unique positive sequence values.

## Submit and decide

Select **Submit for Approval**. Sequential routes activate the first step only;
parallel routes activate all steps.

An assigned pending approver may enter comments on their row, then select:

- **Approve**
- **Request Changes** (comments required)
- **Reject** (comments required)

Change requests and rejections close every activity from that round. Resubmit
after corrections to start a clean round. Previous decisions remain in the
task's internal chatter audit trail.

## Manager controls

- **Reset Approval** clears current decisions and activities but keeps the route.
- **Manager Override** requires a written reason and approves every remaining
  step. The internal chatter records the actor, reason, project, task, and time.

## Allocated time

Enter a value and select **Hours** or **Days**. When Days is selected, choose an
optional calendar. Odoo converts the value into standard allocated hours using:

1. Task Allocation Calendar
2. Main assigned employee's Working Hours
3. Project company's Working Hours
4. 8 hours per day

The synchronized `allocated_hours` value remains available to standard Project,
timesheet, planning, profitability, progress, and reporting features.

## Import sequence

For reliable nested imports:

1. Import or update projects with **Use Task Approval Matrix**.
2. Import tasks/subtasks with **Requires Approval**, **Approval Type**,
   **Allocation Value**, **Allocation Unit**, and **Allocation Calendar**.
3. Import route rows through the approval-line model or use Odoo's nested task
   columns:
   - `Approvers/User`
   - `Approvers/Sequence`
   - `Approvers/Approval Role`
4. Submit tasks using the button after validating routes.

Do not import approval status, submitter, submission date, final approval date,
line decision state, decision user, or decision date. Those values are protected
and produced only by workflow actions.
