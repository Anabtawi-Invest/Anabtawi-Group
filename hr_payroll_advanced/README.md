# hr_payroll_advanced (Odoo 19)

## What it does
- Adds a Reconcile Status badge on payslips (Pending/Reconciled).
- Adds a "Reconcile Lateness" button on payslip form.
- Reconciliation engine consumes lateness in this order: OT -> Annual Leave -> Salary (hours-based).
- Prevents validating payslips and pay runs while reconciliation is Pending.
- Shows a live OT Bank Balance on employee profile (computed from accounting liability lines containing 'OT_TOTAL').

## Notes
- The metrics are computed from Worked Days lines:
  - LAT  = lateness hours
  - OTW/OTR/PHO = overtime hours
- Annual leave hours are derived from employee remaining leaves (days) * hours/day from employee calendar.
