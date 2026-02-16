# Payroll Control Engine (Odoo 19)

Implements the agreed workflow:

- Reads worked days codes:
  - Lateness: LAT (configurable)
  - Overtime: OTW, OTR, PHO (configurable)

- Applies deduction order automatically on **Payslip Done**:
  1) Accrue OT hours to OT Bank (ledger)
  2) Offset lateness from OT Bank (time-for-time)
  3) Offset remaining lateness from Annual Leave (creates leave if configured)
  4) Remaining becomes Unpaid Hours and triggers salary deduction through an input + salary rule.

## Setup
1. Settings → Payroll Control Engine:
   - Select Annual Leave Type (optional but recommended)
   - Confirm codes LAT / OTW,OTR,PHO
2. Ensure your Work Entry / Worked Days codes match the settings.

## Notes
- All dashboard computes are read-only (no writes) to avoid upgrade/registry loops.
- No `category_id` used in res.groups (Odoo 19 safe).
- No `numbercall` in cron (not used).
