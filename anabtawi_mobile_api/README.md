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
