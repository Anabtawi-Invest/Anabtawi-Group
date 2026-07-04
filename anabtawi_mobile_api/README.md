# Anabtawi Employee App API

The employee Profile endpoint exposes the authenticated employee's rotating OTP from the `employee_request` module (`hr.employee.employee_password`) from the required `employee_request` module.

Odoo 19 integration addon for the Anabtawi HR Android/iOS application.

## Required existing addons

- `anabtawi_mobile_single_device`
- `portal_check_in`
- `portal_leaves`
- `hr_attendance_overtime_approval_bridge`
- `employee_request`

The manifest declares these dependencies, so Odoo will refuse installation if any are unavailable.

## Installation

1. Copy `anabtawi_mobile_api` into the configured custom addons directory.
2. Restart all Odoo workers.
3. Update the Apps list.
4. Install or upgrade **Anabtawi Mobile API**.

Command-line example:

```bash
./odoo-bin -d ANABTAWI_DATABASE -i anabtawi_mobile_api --stop-after-init
```

For upgrades, use `-u anabtawi_mobile_api` instead of `-i`.

## Tests

```bash
./odoo-bin -d ANABTAWI_TEST -i anabtawi_mobile_api --test-enable \
  --test-tags /anabtawi_mobile_api --stop-after-init
```

Never run module tests against the production database.


## Profile OTP payload

`GET /anabtawi/mobile/employee/profile` returns the rotating Employee App OTP from
`employee_request`:

```json
{
  "otp_number": "12345",
  "employee_otp": "12345",
  "otp_generated_at": "2026-07-02 12:00:00",
  "otp_source": "employee_request.employee_password"
}
```

The Employee App should display `otp_number` on the Profile screen.
