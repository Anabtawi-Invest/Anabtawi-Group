# Time Off and Extra Hours — Implementor Guide

This document describes how **Time Off** and **Extra Hours** work in the Anabtawi Odoo 19 setup after the Extra Hours Approval enhancement.

Audience: implementors, functional consultants, and support engineers configuring or troubleshooting the Employee App, Attendance, and Time Off.

---

## 1. Time Off (Leave)

### 1.1 Where employees request leave

- Employee App: `/employee-portal` → **Request leave**

### 1.2 Which leave types appear

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

### 1.3 Implementor checklist (Time Off)

1. Add the intended leave types under **Employee Portal / App** settings for the correct company.
2. For types that require allocation, create and approve allocations for the employee.
3. Confirm remaining balance > 0 for that employee.
4. Confirm the employee’s portal/app user is linked to the correct `hr.employee`.
5. Re-test leave balances in the Employee App after login.

---

## 2. Extra Hours — end-to-end process

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

## 3. Status fields — how to read them

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

## 4. Employee App URLs

| Page | URL |
|---|---|
| Employee App home | `/employee-portal` |
| Extra Hours Approval (manager) | `/employee-portal/extra-hours-approval` |

Search on Extra Hours Approval filters pending requests by employee name.

---

## 5. Setup requirements (Extra Hours)

For the manager flow to work:

1. Employee has **Manager** (`parent_id`) set to another employee.
2. That manager employee has a related user (portal is OK) and can log into the Employee App.
3. Company attendance overtime validation is typically **Approved by Manager** for lines to stay pending.
4. Required Extra Hours / Employee App modules are installed and upgraded on the database.

Optional / related:

- Attendance Manager / Second Manager still matter for **Approvals-app pre-authorization** overtime requests.
- Required Weekly Hours still exists under Attendance settings; it no longer controls Extra Hours Approval button visibility.

---

## 6. Troubleshooting

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
- Re-process those attendances after the latest code is deployed so under-45 totals are auto-refused and waiting records are cleared
