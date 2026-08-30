# Fixes & Architecture Tracking Register (`factory_attendance_payroll`)

This document serves as the permanent tracking register for all resolved issues, architectural rules, and performance optimizations implemented in `factory_attendance_payroll`.

---

## 📌 Index of Solved Issues & Architectural Rules

| ID | Issue / Feature | Root Cause | Implemented Solution | File(s) |
|---|---|---|---|---|
| **FIX-01** | **Attendance Gantt View Singleton Crash** (`ValueError: Expected singleton: hr.employee(...)`) | Odoo Gantt controllers pass multi-employee recordsets (`hr.employee(id1, id2, ...)`) to `_get_versions_with_contract_overlap_with_period()`, which had `self.ensure_one()`. | Removed `self.ensure_one()`, added `super()` delegation and fallback searching `('employee_id', 'in', self.ids)`. | `models/hr_employee.py` |
| **FIX-02** | **Slow Module Activation / Upgrade Stalls** | Stored compute fields without state/date check recomputed full database history on upgrade. | Added 60-day historical cutoff in `hr_attendance.py` and filtered `_compute_attendance_reconciliation_fields` to active `draft`/`verify` slips only. | `models/hr_attendance.py`, `models/hr_payslip.py` |
| **FIX-03** | **Slow / Freezing Payslip Cancellation** | Cancelling draft slips triggered database searches across leaves and allocations, plus recursive `write({'is_reconciled': False})` loops. | Added Draft fast-path in `_revert_reconciliation_settlements` to bypass searches when never reconciled, and added `skip_reconcile_revert=True` context flag. | `models/hr_payslip.py` |
| **FIX-04** | **Slow Payslip Computation (`Compute Sheet`)** | Double deletion and recreation of `worked_days_line_ids` (once manually + once by `super().compute_sheet()`), plus unbatched work entry row-by-row writes. | Streamlined `compute_sheet()` into single-pass execution; batched rest day conversion updates into 1 bulk `to_update.write(...)`. | `models/hr_payslip.py` |
| **FIX-05** | **Work Entry Regeneration 24h Error** (`Validation Error: Duration must be positive and cannot exceed 24 hours`) | Creating/updating `hr.work.entry` records with `0.0h` duration or missing `date_start`/`date_stop` timestamps. | Enforced strict positive duration bounds ($0.01\text{h} \le \text{Duration} \le 24.0\text{h}$) and populated explicit `date_start` and `date_stop` datetimes matching the duration. | `models/hr_employee.py` |
| **FIX-06** | **Unapproved Extra Hours Appearing on Payslip** | Public holiday and daily overtime were accumulating into `attendance_gross_overtime` without verifying manager approval status. | Enforced strict check: `total_ot` only accumulates hours if `approved_ot_by_emp_date` exists OR `att.overtime_status == 'approved'` OR `att.validated_overtime_hours > 0`. | `models/hr_payslip.py` |
| **FIX-07** | **Decoupled Leave Transaction Safety** | Creating `hr.leave` / `hr.leave.allocation` during draft calculations caused database bloat and sync issues. | Calculations remain 100% in-memory during draft; database `hr.leave` and `hr.leave.allocation` creation occurs strictly inside `action_payslip_done()`. | `models/hr_payslip.py` |
| **FIX-08** | **Public Holiday Premium Rate & Zero Penalty** | Public holidays generated unworked absence deductions. | Public holidays are detected in bulk; unworked holidays have 0 penalties; worked holidays earn 150% (1.5x) rate when approved. | `models/hr_attendance.py`, `models/hr_payslip.py` |
| **FIX-09** | **4-Day Monthly Absence Grace Rule** | Unpunched days immediately generated deduction work entries. | First 4 unpunched working days per month are forgiven (grace quota); 5th+ day receives an `ABSENT` work entry. | `models/hr_employee.py` |
| **FIX-10** | **Bytecode & Pycache Management** | Compiled `.pyc` and `__pycache__` artifacts caused staging deployment conflicts. | All `__pycache__` directories and `.pyc` files are permanently excluded and cleaned. | Repository Root |

---

## 🔒 Architectural Rules Never to Break

1. **No Database Writes Inside Compute Methods:**
   Never call `write()`, `create()`, or `unlink()` inside `@api.depends` compute methods. Compute methods must only assign values to fields in memory.
2. **No Singleton Assumptions on Gantt/Planning Hooks:**
   Methods invoked by Gantt views or calendar controllers must always handle multi-record recordsets (`self` containing multiple employees/records).
3. **Draft Payslip Fast-Paths:**
   Cancelling or recalculating draft payslips must never perform expensive historical table scans across `hr.leave` or `hr.attendance.overtime.line`.
4. **Work Entry Bounds Protection:**
   Always ensure `0.01 <= duration <= 24.0` and populate valid `date_start` and `date_stop` whenever creating `hr.work.entry` records.
5. **Approval Enforcement on Payslips:**
   Never show or pay overtime/extra hours unless `overtime_status == 'approved'` or `validated_overtime_hours > 0`.
