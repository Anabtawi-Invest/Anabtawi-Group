# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    reconciliation_done = fields.Boolean(
        string="Reconciliation Done",
        default=False,
        readonly=True,
        copy=False,
    )

    reconciliation_ids = fields.One2many(
        "hr.payrun.reconciliation",
        "pay_run_id",
        string="Reconciliation Lines",
        readonly=True,
        copy=False,
    )

    reconciliation_count = fields.Integer(
        compute="_compute_reconciliation_count",
        string="Reconciliation Count",
    )

    def _compute_reconciliation_count(self):
        for run in self:
            run.reconciliation_count = len(run.reconciliation_ids)

    # -------------------------
    # Public Actions (UI)
    # -------------------------

    def action_reconciliation(self):
        """One-click reconciliation that:
        - reads lateness HOURS from work entries in each slip period
        - consumes OT hours (bank) first
        - consumes Annual Leave hours second (creates validated time off)
        - creates payslip inputs for hours ONLY
        - writes a full audit line (hr.payrun.reconciliation)
        """
        for run in self:
            run._prr_assert_can_reconcile()
            run._prr_execute_reconciliation()
            run.reconciliation_done = True
        return True

    def action_reset_reconciliation(self):
        """Rollback reconciliation so HR can regenerate payslips/inputs."""
        for run in self:
            run._prr_assert_can_reset()
            run._prr_rollback_reconciliation()
            run.reconciliation_done = False
        return True

    def action_view_reconciliation_lines(self):
        self.ensure_one()
        action = {
            "type": "ir.actions.act_window",
            "name": _("Reconciliation Lines"),
            "res_model": "hr.payrun.reconciliation",
            "view_mode": "tree,form",
            "domain": [("pay_run_id", "=", self.id)],
            "context": {"default_pay_run_id": self.id},
        }
        return action

    # -------------------------
    # Guards
    # -------------------------

    def _prr_assert_can_reconcile(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("Reconciliation can only be executed when the pay run is in Draft state."))
        if self.reconciliation_done:
            raise UserError(_("Reconciliation has already been executed for this pay run."))

        slips = self.slip_ids
        if not slips:
            raise UserError(_("This pay run has no payslips."))

        # Block confirmed/paid/done slips (upgrade-safe checks)
        blocked_states = set()
        slip_state_field = slips._fields.get("state")
        if slip_state_field:
            # Common states: draft, verify, done, cancel, paid (varies by localization)
            blocked_states = {"done", "paid"}
            bad = slips.filtered(lambda s: s.state in blocked_states)
            if bad:
                raise UserError(_(
                    "Reconciliation cannot run because some payslips are already confirmed/paid.
"
                    "Please reset those payslips to Draft/To Verify first."
                ))

        # Company configuration checks (no hardcoded IDs)
        company = self.company_id
        if not company.prr_lateness_work_entry_type_id:
            raise UserError(_(
                "Missing configuration: Lateness Work Entry Type.
"
                "Go to Settings → Payroll Reconciliation and set it for the current company."
            ))
        if not company.prr_annual_leave_type_id:
            raise UserError(_(
                "Missing configuration: Annual Leave Type (Hours).
"
                "Go to Settings → Payroll Reconciliation and set it for the current company."
            ))

    def _prr_assert_can_reset(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("You can only reset reconciliation while the pay run is in Draft state."))
        if not self.reconciliation_done and not self.reconciliation_ids:
            raise UserError(_("There is no reconciliation to reset."))

        slips = self.slip_ids
        if slips and "state" in slips._fields:
            bad = slips.filtered(lambda s: s.state in {"done", "paid"})
            if bad:
                raise UserError(_(
                    "Rollback is blocked because some payslips are already confirmed/paid.
"
                    "Please reset them first, then retry."
                ))

    # -------------------------
    # Core execution
    # -------------------------

    def _prr_execute_reconciliation(self):
        self.ensure_one()

        # Prevent duplicates using existing lines
        if self.reconciliation_ids:
            raise UserError(_("This pay run already has reconciliation lines. Please reset first."))

        # Preload input types (created by this module data)
        input_type_map = self._prr_get_input_types()

        for slip in self.slip_ids:
            slip._prr_assert_period_dates()
            if slip.company_id != self.company_id:
                # Multi-company boundary protection
                raise UserError(_("Payslip company mismatch detected. Please separate pay runs by company."))

            employee = slip.employee_id
            if employee.company_id and employee.company_id != self.company_id:
                raise UserError(_("Employee %(emp)s belongs to another company.", emp=employee.display_name))

            lateness_hours = self._prr_get_lateness_hours(employee, slip.date_from, slip.date_to)
            if lateness_hours <= 0:
                # Still create an audit line (traceability) with zeros.
                self._prr_create_audit_line(
                    slip=slip,
                    lateness_hours=0.0,
                    ot_used=0.0,
                    annual_used=0.0,
                    late_unpaid=0.0,
                )
                continue

            remaining = lateness_hours

            # 1) Consume OT hours (bank)
            ot_available = self._prr_get_ot_available_hours(employee, slip.date_to)
            ot_used = min(remaining, ot_available)
            remaining -= ot_used

            # 2) Consume Annual Leave hours (create validated time off)
            annual_available = self._prr_get_annual_available_hours(employee, slip.date_to)
            annual_used = min(remaining, annual_available)
            remaining -= annual_used

            late_unpaid = max(remaining, 0.0)

            # Create inputs (hours ONLY)
            ot_input = self._prr_upsert_payslip_input(
                slip=slip,
                input_type=input_type_map["OT_CONSUMED_HOURS"],
                hours=ot_used,
            )
            annual_input = self._prr_upsert_payslip_input(
                slip=slip,
                input_type=input_type_map["ANNUAL_CONSUMED_HOURS"],
                hours=annual_used,
            )
            late_input = self._prr_upsert_payslip_input(
                slip=slip,
                input_type=input_type_map["LATE_UNPAID_HOURS"],
                hours=late_unpaid,
            )

            # Create Annual Leave time off record (validated) ONLY if annual_used > 0
            annual_leave = False
            if annual_used > 0:
                annual_leave = self._prr_create_validated_annual_leave(
                    employee=employee,
                    hours=annual_used,
                    date_from=slip.date_from,
                    date_to=slip.date_to,
                    slip=slip,
                )

            # Create audit line
            self._prr_create_audit_line(
                slip=slip,
                lateness_hours=lateness_hours,
                ot_used=ot_used,
                annual_used=annual_used,
                late_unpaid=late_unpaid,
                ot_input=ot_input,
                annual_input=annual_input,
                late_input=late_input,
                annual_leave=annual_leave,
            )

    def _prr_rollback_reconciliation(self):
        self.ensure_one()
        # Delete created objects referenced by audit lines, then delete audit lines.
        for line in self.reconciliation_ids:
            # Inputs (hours) - safe unlink if still present
            for rec in (line.ot_input_id, line.annual_input_id, line.late_unpaid_input_id):
                if rec and rec.exists():
                    # unlink respects access rights
                    rec.unlink()

            # Annual leave record
            if line.annual_leave_id and line.annual_leave_id.exists():
                leave = line.annual_leave_id
                # Try to refuse/reset before deleting if workflow requires
                if "state" in leave._fields and leave.state in ("validate", "validated"):
                    # Standard in hr_holidays: action_refuse exists
                    if hasattr(leave, "action_refuse"):
                        leave.action_refuse()
                if leave.exists():
                    leave.unlink()

        self.reconciliation_ids.unlink()

    # -------------------------
    # Helper methods
    # -------------------------

    def _prr_get_input_types(self):
        """Return a dict code -> hr.payslip.input.type record."""
        input_types = self.env["hr.payslip.input.type"].search([
            ("code", "in", ["OT_CONSUMED_HOURS", "ANNUAL_CONSUMED_HOURS", "LATE_UNPAID_HOURS"])
        ])
        by_code = {it.code: it for it in input_types}
        missing = [c for c in ["OT_CONSUMED_HOURS", "ANNUAL_CONSUMED_HOURS", "LATE_UNPAID_HOURS"] if c not in by_code]
        if missing:
            raise UserError(_("Missing payroll input types: %s. Please upgrade/reinstall the module.", ", ".join(missing)))
        return by_code

    def _prr_upsert_payslip_input(self, slip, input_type, hours):
        """Create or update a payslip input line. Stores HOURS in 'amount'."""
        PayslipInput = self.env["hr.payslip.input"]

        domain = [("payslip_id", "=", slip.id), ("input_type_id", "=", input_type.id)]
        existing = PayslipInput.search(domain, limit=1)
        vals = {
            "payslip_id": slip.id,
            "input_type_id": input_type.id,
            "amount": float(hours or 0.0),
            "name": input_type.name,
        }
        if existing:
            existing.write(vals)
            return existing
        return PayslipInput.create(vals)

    def _prr_create_audit_line(
        self,
        slip,
        lateness_hours,
        ot_used,
        annual_used,
        late_unpaid,
        ot_input=False,
        annual_input=False,
        late_input=False,
        annual_leave=False,
    ):
        return self.env["hr.payrun.reconciliation"].create({
            "pay_run_id": self.id,
            "employee_id": slip.employee_id.id,
            "payslip_id": slip.id,
            "lateness_hours": float(lateness_hours or 0.0),
            "ot_used_hours": float(ot_used or 0.0),
            "annual_used_hours": float(annual_used or 0.0),
            "late_unpaid_hours": float(late_unpaid or 0.0),
            "execution_datetime": fields.Datetime.now(),
            "executed_by": self.env.user.id,
            "ot_input_id": ot_input.id if ot_input else False,
            "annual_input_id": annual_input.id if annual_input else False,
            "late_unpaid_input_id": late_input.id if late_input else False,
            "annual_leave_id": annual_leave.id if annual_leave else False,
            "state": "applied",
        })

    # -------------------------
    # Lateness (Work Entries)
    # -------------------------

    def _prr_get_lateness_hours(self, employee, date_from, date_to):
        """Sum overlap hours for lateness work entries within [date_from, date_to]."""
        self.ensure_one()
        company = self.company_id
        lateness_type = company.prr_lateness_work_entry_type_id

        WorkEntry = self.env["hr.work.entry"]
        domain = [
            ("employee_id", "=", employee.id),
            ("work_entry_type_id", "=", lateness_type.id),
            ("date_stop", ">", date_from),
            ("date_start", "<", date_to + timedelta(days=1)),  # inclusive end date safety
        ]
        entries = WorkEntry.search(domain)

        total = 0.0
        dt_from = fields.Datetime.to_datetime(date_from)
        dt_to = fields.Datetime.to_datetime(date_to) + timedelta(days=1)
        for we in entries:
            we_start = we.date_start
            we_stop = we.date_stop
            if not we_start or not we_stop:
                continue
            start = max(we_start, dt_from)
            stop = min(we_stop, dt_to)
            if stop <= start:
                continue
            total += (stop - start).total_seconds() / 3600.0
        return total

    # -------------------------
    # OT Availability (Bank)
    # -------------------------

    def _prr_get_ot_available_hours(self, employee, date_to):
        """Get banked OT hours available to consume.

        This module stays upgrade-safe by supporting multiple standard sources:
        1) If employee has a numeric field commonly used for OT bank (extra_hours / overtime_hours), use it.
        2) Otherwise, sum hours from work entries whose types are configured on the company as OT bank types.
        """
        self.ensure_one()

        # Source 1: employee-level numeric bank field if present
        for fname in ("extra_hours", "overtime_hours", "ot_hours", "banked_overtime_hours"):
            if fname in employee._fields:
                val = employee[fname] or 0.0
                try:
                    return float(val)
                except Exception:
                    pass

        # Source 2: configured work entry types for OT
        ot_types = self.company_id.prr_ot_work_entry_type_ids
        if not ot_types:
            # OT is optional; if not configured, treat as 0 and continue priority chain.
            return 0.0

        WorkEntry = self.env["hr.work.entry"]
        dt_to = fields.Datetime.to_datetime(date_to) + timedelta(days=1)

        domain = [
            ("employee_id", "=", employee.id),
            ("work_entry_type_id", "in", ot_types.ids),
            ("date_start", "<", dt_to),
        ]
        entries = WorkEntry.search(domain)

        total = 0.0
        for we in entries:
            if not we.date_start or not we.date_stop:
                continue
            stop = min(we.date_stop, dt_to)
            start = we.date_start
            if stop <= start:
                continue
            total += (stop - start).total_seconds() / 3600.0
        return total

    # -------------------------
    # Annual Leave Availability (Hours)
    # -------------------------

    def _prr_get_annual_available_hours(self, employee, date_to):
        """Return remaining Annual Leave hours available.

        Uses standard hr_holidays APIs with safe fallbacks. If no reliable API is available,
        raises a clear UserError to avoid silent wrong deductions.
        """
        self.ensure_one()
        annual_type = self.company_id.prr_annual_leave_type_id
        if not annual_type:
            return 0.0

        # Prefer standard helper methods if available on leave type
        # (signatures vary across versions; keep safe with try/except).
        if hasattr(annual_type, "get_days"):
            try:
                data = annual_type.get_days(employee.id)
                # Older versions returned dict per employee id
                if isinstance(data, dict):
                    emp_data = data.get(employee.id) or data.get(str(employee.id)) or {}
                    # try known keys
                    for key in ("remaining_leaves", "remaining", "remaining_hours"):
                        if key in emp_data:
                            return float(emp_data[key] or 0.0)
            except TypeError:
                try:
                    data = annual_type.get_days([employee.id])
                    if isinstance(data, dict):
                        emp_data = data.get(employee.id) or {}
                        for key in ("remaining_leaves", "remaining", "remaining_hours"):
                            if key in emp_data:
                                return float(emp_data[key] or 0.0)
                except Exception:
                    pass
            except Exception:
                pass

        # Fallback: use employee leave data method if present
        for mname in ("_get_leave_days_data", "get_leave_days_data"):
            if hasattr(employee, mname):
                try:
                    data = getattr(employee, mname)(annual_type, date_to)
                    if isinstance(data, dict):
                        # Try common patterns
                        for key in ("remaining_leaves", "remaining", "remaining_hours"):
                            if key in data:
                                return float(data[key] or 0.0)
                except Exception:
                    pass

        # Last resort: try validated allocations - validated leaves (hours)
        # Note: field names can differ; we check safely.
        Allocation = self.env["hr.leave.allocation"] if "hr.leave.allocation" in self.env else None
        Leave = self.env["hr.leave"]

        if Allocation and "holiday_status_id" in Allocation._fields:
            alloc_domain = [
                ("employee_id", "=", employee.id),
                ("holiday_status_id", "=", annual_type.id),
            ]
            if "state" in Allocation._fields:
                alloc_domain.append(("state", "=", "validate"))
            allocations = Allocation.search(alloc_domain)
            alloc_hours = 0.0
            for a in allocations:
                for fname in ("number_of_hours_display", "number_of_hours", "number_of_days_display"):
                    if fname in a._fields:
                        alloc_hours += float(a[fname] or 0.0)
                        break

            leave_domain = [
                ("employee_id", "=", employee.id),
                ("holiday_status_id", "=", annual_type.id),
            ]
            if "state" in Leave._fields:
                leave_domain.append(("state", "in", ["validate", "validated"]))
            leaves = Leave.search(leave_domain)
            used_hours = 0.0
            for l in leaves:
                for fname in ("number_of_hours_display", "number_of_hours"):
                    if fname in l._fields:
                        used_hours += float(l[fname] or 0.0)
                        break
            return max(alloc_hours - used_hours, 0.0)

        raise UserError(_(
            "Cannot determine Annual Leave remaining hours using standard APIs.
"
            "Please ensure Annual Leave Type supports hour-based tracking and that allocations exist."
        ))

    def _prr_create_validated_annual_leave(self, employee, hours, date_from, date_to, slip):
        """Create a validated time off request for Annual Leave in hours.

        Purpose: decrease Annual Leave balance automatically (no manual HR steps).
        Stores an auditable record linked in reconciliation line.

        Implementation notes:
        - Odoo supports hour-based time off via request_unit_hours and number_of_hours_display.
        - We keep date range inside the payslip period; the exact hour placement is not critical for balance,
          but we keep it consistent and traceable.
        """
        annual_type = self.company_id.prr_annual_leave_type_id
        if not annual_type:
            return False

        Leave = self.env["hr.leave"]

        vals = {
            "name": _("Payroll Reconciliation (Annual Leave) - %s") % (slip.name or slip.number or slip.id),
            "employee_id": employee.id,
            "holiday_status_id": annual_type.id,
        }

        # Hour-based fields vary; we set safely.
        if "request_unit_hours" in Leave._fields:
            vals["request_unit_hours"] = True
        if "number_of_hours_display" in Leave._fields:
            vals["number_of_hours_display"] = float(hours)
        elif "number_of_hours" in Leave._fields:
            vals["number_of_hours"] = float(hours)
        else:
            # If system does not support hour-based leave, block instead of making wrong record.
            raise UserError(_(
                "Annual Leave consumption requires hour-based time off configuration.
"
                "Your Odoo setup does not expose hour fields on Time Off requests."
            ))

        # Set a minimal date window within payslip period for traceability.
        # We choose the start date at 09:00 local time (server stored as UTC) and extend by needed hours.
        # If request_date_from/to exist, use them; otherwise fallback to date_from/to.
        dt_start = fields.Datetime.to_datetime(date_from)
        if "request_date_from" in Leave._fields:
            vals["request_date_from"] = dt_start
        if "request_date_to" in Leave._fields:
            vals["request_date_to"] = dt_start + timedelta(hours=float(hours))
        if "date_from" in Leave._fields:
            vals["date_from"] = dt_start
        if "date_to" in Leave._fields:
            vals["date_to"] = dt_start + timedelta(hours=float(hours))

        leave = Leave.create(vals)

        # Validate (auto) if possible.
        if hasattr(leave, "action_validate"):
            leave.action_validate()

        # If still not validated, raise error to avoid silent non-deduction.
        if "state" in leave._fields and leave.state not in ("validate", "validated"):
            raise UserError(_(
                "Annual Leave request could not be validated automatically.
"
                "Please check Time Off approval settings and user access rights."
            ))
        return leave


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    def _prr_assert_period_dates(self):
        for slip in self:
            if not slip.date_from or not slip.date_to:
                raise UserError(_("Payslip period is missing date_from/date_to for %s.", slip.employee_id.display_name))
