# Lateness Reconciliation for Odoo 19

This module tracks and reconciles employee lateness during payroll processing in Odoo 19.

## Features
- Auto-detects lateness per payslip
- Logs late check-ins
- Alerts manager if threshold is exceeded
- Mass reconciliation and cron job

## Setup Instructions
1. Clone repo into Odoo addons
2. Restart Odoo and update app list
3. Install from Apps: Lateness Reconciliation

## SQL Optimization
```sql
CREATE INDEX ON hr_attendance(check_in);
CREATE INDEX ON planning_slot(employee_id, start_datetime, end_datetime);
```
