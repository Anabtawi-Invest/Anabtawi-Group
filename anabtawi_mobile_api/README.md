# Anabtawi Mobile API

The employee Profile endpoint exposes the authenticated employee's rotating OTP from the `employee_request` module (`hr.employee.employee_password`) when that field is installed.

Odoo 19 integration addon for the Anabtawi HR Android/iOS application.

## Required existing addons

- `anabtawi_mobile_single_device`
- `portal_check_in`
- `portal_leaves`
- `hr_attendance_overtime_approval_bridge`

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
