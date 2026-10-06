# Payroll Fix Recon (`payroll_fix_recon`)

Clean replacement for `factory_attendance_payroll`. Same business rules, same field names and
salary-rule codes, but the payslip worked days come from one day ledger so counts always match the
work entries and attendance.

## Structure

| File | Responsibility |
|---|---|
| `models/pfr_utils.py` | constants (thresholds, code sets) and pure helpers |
| `models/hr_employee.py` | work station, break policy, manager exemption, contract window |
| `models/hr_attendance.py` | daily net/lateness/overtime metrics, overtime approval |
| `models/pfr_absent_engine.py` | ABSENT work entries + earned rest-day quota, leave work entries, cron |
| `models/pfr_day_ledger.py` | **every calendar day of a payslip -> exactly one bucket** |
| `models/pfr_settlement.py` | overtime figures + 3-step lateness settlement (pure computation) |
| `models/hr_payslip.py` | fields, worked-day lines from the ledger, compute sheet |
| `models/hr_payslip_sync.py` | confirm / cancel: annual settlement leaves, Extra Hours allocation |
| `models/hr_payslip_termination.py` | CLEAR_EXTRA / CLEAR_ANNUAL / CLEAR_PTO inputs |
| `models/hr_payroll_structure.py` | ATT_RECON_VAR, OT_NET, DED_UNDERTIME, ACTUAL rules per structure |

## Worked-day buckets (each day counted once)

`OUT` > `PHD` (worked public holiday) > `WORK` (check-in / attendance entry) > `TRAVEL` > `SICK` /
`UNPAID` / other leave types (work entries) > `PH` (unworked holiday) > `ABSENT` entry > `REST`.

* `WORK100` line = WORK + REST + PH days.
* ABSENT line = days of the actual ABSENT work entries, hours = their duration.
* Lines always add up to the calendar days of the payslip.

## Pay = once

`ACTUAL = paid days x wage / days in month` (paid days = all lines except out-of-contract and unpaid
leave). ABSENT hours are part of the lateness settlement (extra hours -> annual leave -> cash), and the
cash leftover is deducted by `DED_UNDERTIME` at `wage / 240`. An absent day is therefore deducted
exactly once, and not at all when covered by banked Extra Hours.

## Migration

1. `CREATE TABLE pfr_employee_backup AS SELECT id, employee_work_station, break_duration_hours,
   allow_annual_leave_lateness_deduction FROM hr_employee;`
2. Uninstall `factory_attendance_payroll` (the install is blocked while it is present).
3. Install `payroll_fix_recon`; the backup is restored by the post-init hook.
4. Press **Compute Sheet** on draft payslips.
