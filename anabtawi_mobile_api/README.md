# Anabtawi Employee App API

Odoo 19 integration addon for the Anabtawi Employee App.

## Main features

- Employee App login endpoint with bearer token.
- Attendance, leave, overtime, and employee profile APIs.
- Single-device restriction for the Employee App only.
- Registered device, registered IP, last IP, registered date, and last login shown under the employee Settings tab.
- HR Manager can reset the Employee App device so the employee can register a different phone.
- Normal Odoo web login is not restricted and can still be used from multiple devices.

## Required existing addons

- `portal_check_in`
- `portal_leaves`
- `hr_attendance_overtime_approval_bridge`

## Installation / Upgrade

1. Replace the existing `anabtawi_mobile_api` folder in custom addons.
2. Push to Odoo.sh.
3. Upgrade **Anabtawi Employee App API** on staging.

Command-line example:

```bash
./odoo-bin -d ANABTAWI_DATABASE -u anabtawi_mobile_api --stop-after-init
```

## Leave approval flow (19.0.1.7.0)

Employee request -> **manager approves in the app** -> **HR confirms in Odoo** -> employee notified.

Configure the leave types the employees use (Sick Leave, Annual Leave, ...) with
*Time Off Validation = By Employee's Approver and Time Off Officer*, and set the
*Time Off Officer(s)* (HR) on each type. The manager is the employee's **Approver**
(`leave_manager_id`).

| Endpoint | Who | Purpose |
|---|---|---|
| `POST /anabtawi/mobile/leaves/create` | employee | request (optional `attachment` base64, `attachment_name`) |
| `POST /anabtawi/mobile/leaves/cancel` | employee | cancel own request (`id`) |
| `GET  /anabtawi/mobile/leaves/list` | employee | own requests with `stage` (`waiting_manager`, `waiting_hr`, `approved`, `refused`, `cancelled`) |
| `GET  /anabtawi/mobile/manager/leaves/pending` | approver | requests waiting for me |
| `POST /anabtawi/mobile/manager/leaves/approve` | approver | `id`, optional `reason`; moves to HR (type "both") |
| `POST /anabtawi/mobile/manager/leaves/refuse` | approver | `id`, `reason` required |
| `GET  /anabtawi/mobile/notifications/list` | all | inbox (`unread_only`, `limit`) |
| `GET  /anabtawi/mobile/notifications/count` | all | `unread`, `pending_approvals` (poll this) |
| `POST /anabtawi/mobile/notifications/read` | all | `ids` list, or empty = all |
| `GET  /anabtawi/mobile/payslips/list`, `/download?id=` | employee | only payslips HR confirmed (done/paid) |

`/employee/profile` also returns `is_leave_approver`, `pending_approvals`, `unread_notifications`.

Notifications are created for: new request (approver), manager approval (employee + HR officers),
HR confirmation (employee), refusal (employee), payslip confirmed (employee). System leaves created by
`payroll_fix_recon` / `hr_leave_fallback` (`leave_fast_create`) never notify anyone.

Authorization: approve/refuse only accept requests whose employee's Approver is the caller and that are still in
state `confirm`; the approval runs as the manager with `check_state=False` so a "both" type stops at HR.
