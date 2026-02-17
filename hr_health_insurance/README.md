# SW - Health Insurance

## 1) Purpose

`hr_health_insurance` adds health insurance management to HR and payroll.

It allows you to:
- Define insurance grades.
- Define insurance contracts per grade and company, with age-based pricing ranges.
- Register employee/dependent insurance lines directly on the employee form.
- Compute policy amount and monthly employee contribution automatically.
- Deduct health insurance from payslips through an automatically added salary rule.
- Configure the accounting account used for health insurance journal lines.
- Optionally set the employee partner as reference on accounting entries for that account.

---

## 2) Dependencies

From `__manifest__.py`, this module depends on:
- `base`
- `hr`
- `mail`
- `hr_payroll_account`
- `base_payroll_account`

---

## 3) Main Business Objects

### 3.1 `hr.health.grade`
Simple master data table for insurance grades.

Fields:
- `name`: Grade name (example: Grade A, Grade B).

---

### 3.2 `hr.health.contract`
Represents a health insurance contract per company and grade, with effective date range.

Fields:
- `name`
- `company_id`
- `contract_grade_id`
- `start_date`
- `end_date`
- `age_group_ids` (One2many to `hr.health.age.group`)

Rules/constraints:
- `start_date` must be before or equal to `end_date`.
- Contracts cannot overlap for the same company and grade.

---

### 3.3 `hr.health.age.group`
Defines premium amount by age range inside a contract.

Fields:
- `health_contract_id`
- `from_age`
- `to_age`
- `amount`

Rules/constraints:
- `from_age < to_age`.
- Age ranges cannot overlap within the same contract.

---

### 3.4 `health.insurance`
Insurance line linked to an employee. Can represent employee or dependent.

Fields:
- `employee_id`
- `relationship` (`employee`, `spouse`, `child`, `parent`)
- `name`, `birthdate`, `gender`, `marital_status_info`, `notes`
- `grade_id`
- `effective_date`
- `age` (computed from `birthdate`)
- `policy_full_amount` (computed from active contract + age range)
- `employee_contribution` (%)
- `monthly_contribution` (computed)
- `manual_contribution` (fixed amount override during payroll calculation)

Behavior:
- If relationship is `employee`, onchange copies:
  - `name` from employee name
  - `birthdate` from employee birthday
  - `gender` from employee sex field
- If relationship is not `employee`, those fields are cleared for manual input.

Computations:
- `policy_full_amount`: finds matching contract by:
  - same grade
  - `start_date <= effective_date <= end_date`
  - age in one age group range
- `monthly_contribution`:
  - `(policy_full_amount * employee_contribution / 100) / 12`

---

### 3.5 `res.company` / `res.config.settings` additions

Company fields:
- `hi_account_id`: Health insurance account.
- `hi_reference_employee_in_journal_entries`: Boolean flag.

Settings fields (related to company):
- `hi_account_id`
- `hi_reference_employee_in_journal_entries`

Settings view adds a **Health Insurance Configuration** block in Payroll settings.

---

### 3.6 `hr.employee` extension

Adds:
- `health_insurance_ids` (One2many to `health.insurance`)

On employee birthday change:
- updates `birthdate` in the related insurance line where `relationship = employee`.

---

## 4) UI and Menus

### Configuration menus
Parent menu:
- `Human Resources > Configuration > Health Insurance`

Submenus:
- `Insurance Grades`
- `Insurance Contracts`

### Employee form integration
In employee form (`Personal Information` page), a **Health Insurance** editable list is added where you maintain insurance lines for employee/dependents.

---

## 5) Payroll Integration

When payroll structure default rules are generated, this module adds a salary rule:
- Name: `Health Insurance`
- Code: `HINSURN`
- Category: `DED` (deduction)

Condition:
- Applied when the sum of employee insurance monthly contributions is greater than zero.

Amount logic:
- For each insurance line:
  - If `manual_contribution > 0`: use manual amount directly.
  - Else if `effective_date` is within payslip period: prorate monthly contribution by valid days.
  - Else if `effective_date <= payslip start`: take full monthly contribution.
- Final result is negative (deduction).

---

## 6) Accounting Integration

In payslip accounting line preparation:
- If `hi_reference_employee_in_journal_entries` is enabled **and**
- the journal line account is `hi_account_id`,

then `partner_id` is set to employee partner (`user partner`, fallback `work_contact_id`).

This helps track health insurance deductions by employee partner on accounting entries.

---

## 7) Security and Access

Access (`ir.model.access.csv`):
- `hr.group_hr_user` has full CRUD on:
  - `health.insurance`
  - `hr.health.grade`
  - `hr.health.contract`
  - `hr.health.age.group`
- Regular internal users (`base.group_user`) have read-only access on:
  - `health.insurance`
  - `hr.health.grade`
  - `hr.health.contract`

Record rule (`rules.xml`):
- Health contracts are restricted to user companies:
  - company is empty OR in current user company set.

---

## 8) Setup and Usage Flow

1. Go to `Human Resources > Configuration > Health Insurance > Insurance Grades`.
   - Create required grades.
2. Go to `Insurance Contracts`.
   - Create contract per grade/company/date range.
   - Add age group ranges and amounts.
3. Go to `Settings` (Payroll/HR settings block added by module).
   - Set `Health Account`.
   - Enable/disable `Health Reference Employee In Journal Entries`.
4. Open an employee.
   - Add/update lines in **Health Insurance** table.
   - Set relationship, grade, effective date, contribution %, and manual contribution if needed.
5. Generate payslip.
   - Rule `HINSURN` calculates and deducts insurance automatically.
6. Post payroll entries.
   - If configured, partner is set on health insurance account lines.

---

## 9) Important Notes

- Age is computed as `today.year - birth_year` (simple yearly difference).
- The module relies on correct contract date ranges and non-overlapping age brackets.
- `manual_contribution` acts as payroll override amount for that line.
- In Odoo 19, employee gender source is `employee.sex` (already adapted in this codebase).

---

## 10) Troubleshooting

- **Module install error about unknown account field**
  - Ensure settings domain uses `active` (not deprecated legacy fields).
- **Onchange error on employee gender**
  - Ensure code reads `employee.sex` in Odoo 19.
- **No deduction in payslip**
  - Verify insurance lines exist.
  - Verify `monthly_contribution`/`manual_contribution` values.
  - Verify salary structure includes default rule `HINSURN`.
- **Wrong accounting partner on move lines**
  - Check `Health Account` and `Health Reference Employee In Journal Entries` settings.

