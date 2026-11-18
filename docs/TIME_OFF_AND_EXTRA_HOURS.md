# Time Off and Extra Hours — Implementor Guide

This document describes how **Time Off** and **Extra Hours** work in the Anabtawi Odoo 19 setup after the Extra Hours Approval enhancement.

Audience: implementors, functional consultants, and support engineers configuring or troubleshooting the Employee App, Attendance, and Time Off.

---

## 1. Modules involved

| Area | Module technical name | Role |
|---|---|---|
| Employee App UI | `anabtawi_employee_app_pwa` | PWA at `/employee-portal` |
| Employee App API | `anabtawi_mobile_api` | Mobile/API endpoints for leave, overtime, extra hours |
| Portal / App leave types | `portal_leaves` | Settings list of leave types shown in portal/app |
| Portal attendance | `portal_check_in` | Check-in/out and related overtime authorization hooks |
| Extra Hours Approval | `hr_attendance_overtime_approval_bridge` | Manager unlock step + Approvals bridge for pre-auth OT |
| Weekly hours setting | `hr_attendance_weekly_overtime_eligibility` | Required weekly hours (still used for some OT gates, **not** for attendance Approve/Refuse visibility) |
| Credited extra hours | `extra_hours_enhancement` | Rates / credited hours for payroll balances |
| Payroll overtime | `anabtawi_payroll_overtime` | Paying overtime from payslip inputs |

Install/upgrade order for Extra Hours Approval work:

1. `hr_attendance_weekly_overtime_eligibility`
2. `hr_attendance_overtime_approval_bridge`
3. `anabtawi_mobile_api`
4. `anabtawi_employee_app_pwa`

---

## 2. Time Off (Leave)

### 2.1 Where employees request leave

- Employee App: `/employee-portal` → **Request leave**
- Portal leave pages from `portal_leaves` (same type rules)

### 2.2 Which leave types appear

Configured in backend:

**Settings → Time Off → Employee Portal / App → Time off types in the portal and Employee App**

Only types listed there are candidates for the app/portal.

Then each employee only sees a type if:

1. The type is active, and
2. Either:
   - the type does **not** require allocation, or
   - the type **requires allocation** and the employee has **remaining balance > 0**

If nothing passes that filter, the app shows **No available leave types**.

Important:

- Saving the list on company A does not help employees of company B.
- Paid / Sick types that require allocation will stay hidden until the employee has an approved allocation with remaining days/hours.

### 2.3 API used by the app

- `GET /anabtawi/mobile/leaves/balances` — types + balances for the logged-in employee
- `POST /anabtawi/mobile/leaves/create` — create a leave request
- `GET /anabtawi/mobile/leaves/list` — employee’s leave history

Eligibility is resolved by:

`res.company._anabtawi_leave_types_for_employee(employee)` in `portal_leaves`.

### 2.4 Implementor checklist (Time Off)

1. Add the intended leave types under **Employee Portal / App** settings for the correct company.
2. For types that require allocation, create and approve allocations for the employee.
3. Confirm remaining balance > 0 for that employee.
4. Confirm the employee’s portal/app user is linked to the correct `hr.employee`.
5. Re-test leave balances in the Employee App after login.

---

## 3. Extra Hours — end-to-end process

There are **two different overtime concepts**. Do not mix them.

### A) Pre-authorization overtime request (Approvals app)

Employee can request overtime **before or around** work from the Employee App / portal using overtime categories (`approval.category` with `is_overtime_category`).

- Creates an `approval.request`
- Approvers historically come from Attendance Manager / Second Manager (internal users)
- Used for pre-authorization / authorization of overtime sessions
- Still exists; it is **not** the same as Extra Hours Approval below

### B) Extra Hours Approval after attendance (current company procedure)

This is the process that unlocks attendance **Approve / Refuse** for worked extra hours.

#### Step 1 — Employee works and checks out

Odoo creates attendance overtime lines when worked time exceeds the schedule.

#### Step 2 — Under 45 minutes: auto refuse

Threshold: **45 minutes = 0.75 hours**.

Compare the **total extra hours of that attendance** (sum of all overtime lines linked to that check-in), not each line alone.

| Total extra hours | Result |
|---|---|
| `< 45 minutes` | Overtime lines are **refused automatically**. No Extra Hours Approval record. No manager step. |
| `≥ 45 minutes` | Create one Extra Hours Approval record in state **Waiting manager approval**. |

#### Step 3 — Manager decision (portal-friendly)

Manager is the employee’s **Manager** field (`hr.employee.parent_id`), not Attendance Manager.

- That manager can be a **portal user** (employee with portal login).
- Record model: `hr.attendance.extra.hours.approval`
- Backend menu: **Attendances → Extra Hours Approval**
- Employee App page: `/employee-portal/extra-hours-approval` (also from home **Extra hours**)
- API:
  - `GET /anabtawi/mobile/extra-hours/pending` (optional `?employee=name`)
  - `POST /anabtawi/mobile/extra-hours/decide` with `{ "id": ..., "decision": "approve"|"refuse" }`

Manager actions:

| Manager action | Attendance badge (`extra_hours_approval_state`) | Attendance Approve/Refuse buttons |
|---|---|---|
| Waiting | Waiting manager approval | Hidden |
| Approve | Approved | Can appear (if status allows) |
| Refuse | Refused by manager | Stay hidden; overtime refused |

**Approved** on the attendance list means: *manager unlocked the record*. It does **not** mean validated Extra Hours were already accepted by Attendance.

#### Step 4 — Attendance officer validates Extra Hours

After Extra Hours Approval = **Approved**, the standard Attendance buttons appear next to Extra Hours:

- Form: check / X beside Extra Hours and on Overtime Details rows
- Management list: check / X on the line

Who can click them:

- Attendance officer/manager rights (`is_manager` on the attendance)

What the buttons do:

- Approve → validates overtime lines / sets attendance overtime to approved
- Refuse → refuses overtime lines

Until the officer approves, **Worked Extra** may show a value while **Extra Hours** (validated) stays `00:00`.

---

## 4. Status fields — how to read them

On `hr.attendance`:

| Field | Meaning |
|---|---|
| Worked Extra / `overtime_hours` | Computed worked overtime |
| Extra Hours / `validated_overtime_hours` | Validated overtime after attendance Approve |
| `overtime_status` | Standard OT status: To Approve / Approved / Refused |
| Extra Hours Approval / `extra_hours_approval_state` | Manager unlock: Waiting / Approved / Refused by manager |

Typical healthy path for ≥ 45 minutes:

1. Checkout → overtime lines `to_approve`, Extra Hours Approval = **Waiting**
2. Manager approves → Extra Hours Approval = **Approved**, buttons appear
3. Officer approves → Extra Hours filled, overtime approved

---

## 5. Employee App URLs

| Page | URL |
|---|---|
| Employee App home | `/employee-portal` |
| Extra Hours Approval (manager) | `/employee-portal/extra-hours-approval` |

Search on Extra Hours Approval filters pending requests by employee name.

---

## 6. Setup requirements (Extra Hours)

For the manager flow to work:

1. Employee has **Manager** (`parent_id`) set to another employee.
2. That manager employee has a related user (portal is OK) and can log into the Employee App.
3. Company attendance overtime validation is typically **Approved by Manager** for lines to stay pending.
4. Modules above are installed and upgraded on the database.

Optional / related:

- Attendance Manager / Second Manager still matter for **Approvals-app pre-authorization** overtime requests.
- Required Weekly Hours still exists under Attendance settings; it no longer controls Extra Hours Approval button visibility.

---

## 7. Shell helpers (implementors)

Create/update Extra Hours Approval for attendances from 1 October until now (manual only; **not** run on module upgrade):

```python
env.cr.rollback()
from odoo import fields
model = env["hr.attendance.extra.hours.approval"]
since = fields.Datetime.to_datetime("2026-10-01 00:00:00")
attendances = env["hr.attendance"].sudo().search([
    ("check_out", "!=", False),
    ("check_in", ">=", since),
    ("overtime_status", "=", "to_approve"),
])
print("attendances:", len(attendances))
created = model._ensure_for_attendances(attendances)
env.cr.commit()
print("done", len(created))
```

Clean waiting approvals under 45 minutes:

```python
env.cr.rollback()
Approval = env["hr.attendance.extra.hours.approval"].sudo()
waiting = Approval.search([("state", "=", "waiting"), ("extra_hours", "<", 0.75)])
print("to clean:", len(waiting))
for approval in waiting:
    Approval._auto_refuse_below_threshold(approval.attendance_id.linked_overtime_ids, approval)
env.cr.commit()
print("done")
```

Or call the built-in helper (October → now, includes 45-minute rule):

```python
env["hr.attendance.extra.hours.approval"]._backfill_waiting_approvals()
env.cr.commit()
```

---

## 8. Troubleshooting

### Leave balances show “No available leave types”

- Types not added in Settings for the employee’s company
- Types require allocation and employee remaining is 0 / no allocation
- Wrong company context when saving settings

### Extra Hours Approval missing for a day

- Total extra hours under 45 minutes → auto refused by design
- Attendance not checked out
- No overtime lines generated (schedule / calendar)
- Manager `parent_id` empty (record can still exist; manager app list filters by `manager_id`)

### Attendance Approve/Refuse not visible

- Extra Hours Approval is not **Approved** yet
- User is not attendance officer / not that employee’s attendance manager
- Overtime status is empty (no lines)

### Badge says Approved but Extra Hours is 00:00

- Manager unlocked the record
- Attendance officer has not validated Extra Hours yet

### Old under-45 records still in manager app

- Created before the 45-minute rule
- Run the cleanup shell script above after the latest code is deployed

---

## 9. Design decisions (current)

1. Extra Hours Approval is a **custom menu/model**, not the Approvals app, so portal managers can decide.
2. Manager source is **employee Manager (`parent_id`)**.
3. Threshold is **total attendance extra hours**, not per line.
4. Module upgrades **do not** auto-backfill historical Extra Hours Approval records (removed for performance). Use shell when needed.
5. Pre-authorization overtime via Approvals remains available for request-before-work scenarios.

---

## 10. Quick process diagram

```text
Employee checks out
        |
        v
Extra hours computed on attendance
        |
        +-- total < 45 min ----> auto refuse overtime lines (stop)
        |
        +-- total >= 45 min --> Extra Hours Approval = Waiting
                                    |
                                    v
                         Manager approves/refuses
                         (Employee App or Attendances menu)
                                    |
                 +------------------+------------------+
                 |                                     |
                 v                                     v
           Approved                              Refused by manager
                 |                                     |
                 v                                     v
   Attendance Approve/Refuse appear            buttons stay hidden
                 |
                 v
        Officer validates Extra Hours
```
