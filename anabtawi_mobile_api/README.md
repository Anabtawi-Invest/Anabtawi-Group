# Anabtawi Employee App API

Self-contained Odoo 19 API for the Employee App. It provides authentication, rotating access/refresh tokens, one-device enforcement, device metadata, employee OTP, attendance, leave, and overtime endpoints.

## Dependencies

- `employee_request`
- `portal_check_in`
- `portal_leaves`
- `hr_attendance_overtime_approval_bridge`

It does **not** depend on `anabtawi_mobile_single_device` and does not restrict ordinary `/odoo` browser sessions.

## Deployment

1. Back up and test on the Odoo.sh staging branch.
2. Remove the legacy `anabtawi_mobile_single_device` code/module using an approved Odoo migration procedure.
3. Install or upgrade `anabtawi_mobile_api`.
4. The `19.0.1.3.0` migration revokes legacy tokens; employees register their current phone on the next login.
5. HR managers can reset a device from **Employees → Employee App → Devices**.

Token lifetimes are configurable with:

- `anabtawi_mobile.access_token_ttl_minutes` (default 60)
- `anabtawi_mobile.refresh_token_ttl_days` (default 30)
- `anabtawi_mobile.token_pepper` (created automatically)

Never run module tests against production.
