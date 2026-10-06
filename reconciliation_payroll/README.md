# Reconciliation Payroll (`reconciliation_payroll`)

Standalone Odoo 19 module for unified attendance reconciliation, schedule-aware break deductions, 3-step lateness settlement, flexible and fixed rest-day quota management, and payroll work entry synchronization.

---

## 🎯 Architectural Overview & Simplifications

This module replaces the legacy monolithic `factory_attendance_payroll` codebase with a clean, high-performance, conflict-free structure:

1. **Clean Model Architecture**:
   - Eliminated redundant backup files (`- Copy.py`), duplicate model inheritance blocks (`res_company` declared across multiple files), and circular write loops.
   - Decoupled `hr.payslip`, `hr.employee`, and `hr.attendance` logic into clear, single-responsibility methods.
2. **Safe Multi-Record Operations**:
   - Contract and calendar overlap helper methods (`_get_versions_with_contract_overlap_with_period`) support multi-employee recordsets safely without singleton crashes in Gantt or Planning views.
3. **No In-Compute Database Writes**:
   - Calculations remain 100% in-memory during draft state. Permanent leave allocations and deductions are synced only when payslips are confirmed (`action_payslip_done()`).
4. **Draft Fast Reversion**:
   - Payslip cancellation, drafting, or unlinking bypasses heavy database scans and cleanly resets reconciliation allocations without deadlocks.

---

## ⚙️ Core Business Logic

### 1. Shift & Lunch Break Deductions
- **Station Defaults**:
  - `Headoffice`: Default break duration = **0.5h (30 min)**.
  - `Retail` / `Factory`: Default break duration = **1.0h (60 min)**.
  - `break_duration_hours`: Configurable per employee.
- **Deduction Thresholds**:
  - Shift duration $\ge 6.0\text{h}$: Full lunch break deducted.
  - $4.0\text{h} < \text{Shift duration} < 6.0\text{h}$: Half lunch break deducted ($0.25\text{h}$ / $0.5\text{h}$).
  - Shift duration $\le 4.0\text{h}$: $0$ break deducted.

### 2. Schedule-Aware Lateness & Overtime
- **Thresholds**:
  - Overtime eligibility: excess $\ge 0.75\text{h}$ ($45$ minutes).
  - Lateness threshold: deficit $\ge 0.25\text{h}$ ($15$ minutes grace period).
- **Shift Types**:
  - **Fixed Schedule** (`headoffice`): Evaluated against calendar working hours or published `planning.slot`. Lateness captures check-in delay + early check-out. Overtime captures late check-out.
  - **Flexible Schedule** (`factory`, `retail`): Evaluated against standard $8.0\text{h}$ daily target based on net worked hours.
- **Manager Exemption**:
  - Employees marked as Manager are exempt from hourly lateness and overtime deductions, but unpunched full working days still generate absence entries.
- **Public Holidays**:
  - Unworked: $0$ penalty, included as paid base attendance.
  - Worked: Net worked hours count as Extra Hours at **1.5x (150%)** rate when approved.

### 3. Rest Day Quota & Absent Work Entry Generation
- Evaluates period month by month:
  - Out of contract days, public holidays, punched days, and approved leave days are excluded from absence.
  - **Earned Rest Days**: $1$ rest day earned per $6$ physical worked days (`min(month_target_weekdays, checkins // 6)`):
    - `Factory`: Evaluates Mondays (`weekday == 0`).
    - `Retail`: Evaluates Fridays (`weekday == 4`).
    - `Headoffice`: Non-working calendar days (e.g. Friday/Saturday).
  - Earned rest days are kept empty (no absence deduction).
  - Candidate unpunched working days exceeding the rest day quota receive an `ABSENT` work entry ($8.0\text{h}$ duration).

### 4. 3-Step Lateness Settlement Engine
1. **Step 1 (Extra Hours)**: Lateness hours are covered using total available Extra Hours balance (previous banked balance + current approved overtime).
2. **Step 2 (Annual Leave)**: Remaining lateness is covered from Annual Leave balance (if employee opted in via `allow_annual_leave_lateness_deduction`).
3. **Step 3 (Cash Deduction)**: Final remaining lateness shortfall is deducted from cash salary (`undertime_cash_deduction_hours`) via salary rule `DED_UNDERTIME`.

### 5. Salary Rules
- `ATT_RECON_VAR`: Informational variance tracking ($0.0\text{ JOD}$).
- `OT_NET`: Net reconciled overtime banked to Extra Hours ($0.0\text{ JOD}$ cash payout).
- `DED_UNDERTIME`: Undertime cash deduction: $-(\text{deficit\_hours} \times \frac{\text{Wage}}{240.0})$.
- `ACTUAL`: Actual Salary: $\text{Paid Days} \times \frac{\text{Wage}}{\text{Days In Month}}$.
