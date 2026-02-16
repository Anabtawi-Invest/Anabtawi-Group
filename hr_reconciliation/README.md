# HR Payroll Reconciliation Dashboard (Odoo 19) — Enterprise Safe

## What this module does
Adds a simple, stable reconciliation dashboard for HR to review **before payroll finalization**:

- Lateness Hours (from Work Entry code `LAT`)
- OT Total Hours (from Work Entry codes `OTW`, `OTR`, `PHO`)
- Annual Leave Hours (employee remaining annual leave days converted to hours)
- Remaining After Reconciliation (Hours) — filled when HR clicks Reconciliation

It also adds:
- A **Reconciliation** button on the Payslip
- A **Mass Reconciliation** button on the Pay Run (batch)

## Key design points (simple & error-free)
- Does **not** modify Work Entries.
- Does **not** create Time Off requests automatically.
- Stores a running OT bank balance in hours on the Employee (`overtime_bank_hours`).
- Reconciliation is allowed only in **Draft / Waiting** states.

## Required Work Entry Codes
Create these Work Entry Types in Payroll configuration:
- Lateness: `LAT`
- OT Weekdays: `OTW`
- OT Weekend: `OTR`
- OT Holiday: `PHO`

## Install
1. Copy folder `hr_reconciliation_v19_1_enterprise_safe` into your custom addons.
2. Update Apps list.
3. Install module.

## Usage
1. Create Pay Run → Generate Payslips.
2. HR reviews the list columns.
3. Press **Mass Reconciliation** (or per payslip **Reconciliation**).
4. Remaining hours are displayed in the payslip and list view.

