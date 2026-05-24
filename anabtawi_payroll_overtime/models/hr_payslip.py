from datetime import datetime, timedelta
import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    termination_clearance = fields.Boolean(
        string="Termination Clearance / مخالصة تيرمنيشن",
        help="Automatically fills termination-related salary inputs.",
    )
    employee_extra_hours_balance = fields.Float(
        string="Extra Hours Balance",
        compute="_compute_employee_extra_hours_balance",
        help="Current remaining employee extra hours balance.",
    )
    overtime_hours_deducted = fields.Float(
        string="Deducted Overtime Hours",
        readonly=True,
        copy=False,
    )
    overtime_deduction_line_id = fields.Many2one(
        "hr.attendance.overtime.line",
        string="Overtime Deduction Entry",
        readonly=True,
        copy=False,
    )
    overtime_restore_line_id = fields.Many2one(
        "hr.attendance.overtime.line",
        string="Overtime Restore Entry",
        readonly=True,
        copy=False,
    )

    @api.depends("employee_id")
    def _compute_employee_extra_hours_balance(self):
        for slip in self:
            computed_balance = slip._get_employee_extra_hours_balance()
            _logger.info(
                "Compute extra hours balance: payslip=%s employee=%s computed_balance=%s",
                slip.id, slip.employee_id.id if slip.employee_id else None, computed_balance,
            )
            slip.employee_extra_hours_balance = computed_balance

    def _get_employee_extra_hours_balance(self):
        self.ensure_one()
        if not self.employee_id:
            _logger.info("Get extra hours balance: payslip=%s has no employee, return 0.0", self.id)
            return 0.0
        remaining = self._get_remaining_extra_hours_from_attendance()
        final_balance = max(0.0, remaining)
        _logger.info(
            "Get extra hours balance: payslip=%s employee=%s remaining_raw=%s final_balance=%s",
            self.id, self.employee_id.id, remaining, final_balance,
        )
        return final_balance

    def _get_remaining_extra_hours_from_attendance(self):
        """Match the 'Remaining Extra Hours' figure from attendance data directly."""
        self.ensure_one()
        overtime_line_model = self.env["hr.attendance.overtime.line"].sudo()
        overtime_metric = (
            "credited_duration"
            if "credited_duration" in overtime_line_model._fields
            else "manual_duration"
        )

        overtime_data = overtime_line_model.read_group(
            domain=[
                ("employee_id", "=", self.employee_id.id),
                ("compensable_as_leave", "=", True),
                ("status", "=", "approved"),
            ],
            fields=[f"{overtime_metric}:sum"],
            groupby=[],
        )
        approved_overtime = overtime_data[0].get(f"{overtime_metric}_sum", 0.0) if overtime_data else 0.0

        leaves_data = self.env["hr.leave"].sudo().read_group(
            domain=[
                ("holiday_status_id.overtime_deductible", "=", True),
                ("holiday_status_id.requires_allocation", "=", False),
                ("employee_id", "=", self.employee_id.id),
                ("state", "not in", ["refuse", "cancel"]),
            ],
            fields=["number_of_hours:sum"],
            groupby=[],
        )
        consumed_in_leaves = leaves_data[0].get("number_of_hours_sum", 0.0) if leaves_data else 0.0

        allocations_data = self.env["hr.leave.allocation"].sudo().read_group(
            domain=[
                ("holiday_status_id.overtime_deductible", "=", True),
                ("employee_id", "=", self.employee_id.id),
                ("state", "in", ["confirm", "validate", "validate1"]),
            ],
            fields=["number_of_hours_display:sum"],
            groupby=[],
        )
        consumed_in_allocations = allocations_data[0].get("number_of_hours_display_sum", 0.0) if allocations_data else 0.0

        remaining = approved_overtime - consumed_in_leaves - consumed_in_allocations
        _logger.info(
            "Remaining extra hours from attendance: payslip=%s employee=%s metric=%s approved_overtime=%s consumed_leaves=%s consumed_allocations=%s remaining=%s",
            self.id,
            self.employee_id.id,
            overtime_metric,
            approved_overtime,
            consumed_in_leaves,
            consumed_in_allocations,
            remaining,
        )
        return remaining

    def _message_overtime_exceeds_balance(self, requested_hours, balance_hours):
        self.ensure_one()
        return _(
            "You cannot pay more extra hours than the available balance. "
            "Requested: %(requested).2f h, available: %(balance).2f h (employee: %(employee)s).\n"
            "لا يمكن صرف ساعات إضافية أكبر من الرصيد المتاح. المطلوب: %(requested).2f س، المتاح: %(balance).2f س (الموظف: %(employee)s)."
        ) % {
            "requested": requested_hours,
            "balance": balance_hours,
            "employee": self.employee_id.name or "",
        }

    def _get_input_type_by_code(self, code):
        self.ensure_one()
        input_type = self.env["hr.payslip.input.type"].search([("code", "=", code)], limit=1)
        if not input_type:
            raise ValidationError(
                _("Salary Input Type with code '%s' was not found. Please create/configure it first.") % code
            )
        return input_type

    def _get_termination_leave_amount(self):
        self.ensure_one()
        employee = self.employee_id
        if not employee:
            return 0.0

        # Prefer the real Time Off balance first (same source as Annual Leave dashboard).
        leave_type = self._get_termination_annual_leave_type()
        if leave_type and hasattr(employee, "_get_consumed_leaves"):
            consumed_data, _to_recheck = employee._get_consumed_leaves(
                leave_type,
                target_date=self.date_to or fields.Date.today(),
            )
            leave_content = consumed_data.get(employee, {}).get(leave_type, {})
            leave_value = sum(
                values.get("virtual_remaining_leaves", 0.0)
                for values in leave_content.values()
            )
            if leave_type.request_unit in ("day", "half_day"):
                leave_value *= employee.resource_calendar_id.hours_per_day or 0.0
            return leave_value

        # Fallback to custom employee fields if no leave type/source is configured.
        if "annual_leave_balance" in employee._fields:
            return employee.annual_leave_balance or 0.0
        if "annual_leave_balance_hours" in employee._fields:
            return employee.annual_leave_balance_hours or 0.0
        if "remaining_annual_leave_balance_hours" in employee._fields:
            return employee.remaining_annual_leave_balance_hours or 0.0

        raise ValidationError(
            _(
                "Unable to determine annual leave balance from employee profile. "
                "Please configure an Annual Leave type (or set one of these employee fields: "
                "annual_leave_balance, annual_leave_balance_hours, remaining_annual_leave_balance_hours)."
            )
        )

    def _get_termination_annual_leave_type(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        if "lateness_annual_leave_type_id" in company._fields and company.lateness_annual_leave_type_id:
            return company.lateness_annual_leave_type_id
        return self.env["hr.leave.type"].search([
            ("name", "ilike", "annual"),
        ], limit=1) or self.env["hr.leave.type"].search([
            ("name", "ilike", "vacation"),
        ], limit=1) or self.env["hr.leave.type"].search([
            ("name", "ilike", "سنوي"),
        ], limit=1)

    def _get_termination_extra_hours_value(self):
        self.ensure_one()
        if not self.employee_id:
            return 0.0
        # Must match the same value shown on payslip Other Info tab.
        return self._get_employee_extra_hours_balance()

    def _apply_termination_clearance_inputs(self):
        input_model = self.env["hr.payslip.input"]
        for slip in self:
            if not slip.termination_clearance or not slip.employee_id:
                continue

            rem_leave_type = slip._get_input_type_by_code("REM_LEAVE")
            eoc_type = slip._get_input_type_by_code("ETH_PAY_EOC")

            if not eoc_type.overtime_quantity_type:
                raise ValidationError(
                    _(
                        "Input Type 'ETH_PAY_EOC' must have 'Use Quantity for Overtime' enabled."
                    )
                )

            rem_leave_value = slip._get_termination_leave_amount()
            eoc_value = slip._get_termination_extra_hours_value()

            rem_leave_line = slip.input_line_ids.filtered(lambda l: l.input_type_id == rem_leave_type)[:1]
            eoc_line = slip.input_line_ids.filtered(lambda l: l.input_type_id == eoc_type)[:1]

            rem_leave_vals = {
                "payslip_id": slip.id,
                "input_type_id": rem_leave_type.id,
                "amount": 0.0,
                "quantity": rem_leave_value,
            }
            eoc_vals = {
                "payslip_id": slip.id,
                "input_type_id": eoc_type.id,
                "quantity": eoc_value,
            }

            if rem_leave_line:
                rem_leave_line.write(rem_leave_vals)
            else:
                if slip.id:
                    input_model.create(rem_leave_vals)
                else:
                    slip.input_line_ids += input_model.new({
                        "input_type_id": rem_leave_type.id,
                        "amount": 0.0,
                        "quantity": rem_leave_value,
                    })

            if eoc_line:
                eoc_line.write(eoc_vals)
            else:
                if slip.id:
                    input_model.create(eoc_vals)
                else:
                    slip.input_line_ids += input_model.new({
                        "input_type_id": eoc_type.id,
                        "quantity": eoc_value,
                    })

    @api.onchange("termination_clearance", "employee_id", "date_to")
    def _onchange_termination_clearance(self):
        for slip in self:
            if slip.termination_clearance and slip.employee_id:
                slip._apply_termination_clearance_inputs()

    def _get_overtime_quantity_to_deduct(self):
        self.ensure_one()
        return sum(
            self.input_line_ids.filtered("overtime_quantity_type").mapped("quantity")
        )

    def _prepare_overtime_balance_line_vals(self, quantity_signed):
        self.ensure_one()
        date_value = self.date_to or fields.Date.context_today(self)
        date_dt = datetime.combine(date_value, datetime.min.time())
        return {
            "employee_id": self.employee_id.id,
            "date": date_value,
            "duration": quantity_signed,
            "manual_duration": quantity_signed,
            "time_start": date_dt,
            "time_stop": date_dt + timedelta(minutes=1),
            "amount_rate": 1.0,
            "status": "approved",
            "compensable_as_leave": True,
        }

    def _deduct_extra_hours_balance(self):
        overtime_line_model = self.env["hr.attendance.overtime.line"].sudo()
        for slip in self:
            if slip.overtime_deduction_line_id:
                _logger.info(
                    "Payslip %s skipped overtime deduction: already linked to line %s",
                    slip.id, slip.overtime_deduction_line_id.id,
                )
                continue
            quantity = slip._get_overtime_quantity_to_deduct()
            if quantity <= 0:
                _logger.info("Payslip %s skipped overtime deduction: overtime quantity is %s", slip.id, quantity)
                continue
            current_balance = slip._get_employee_extra_hours_balance()
            if quantity > current_balance + 1e-6:
                raise ValidationError(slip._message_overtime_exceeds_balance(quantity, current_balance))
            _logger.info(
                "Payslip %s overtime deduction start: employee=%s quantity=%s balance_before=%s",
                slip.id, slip.employee_id.id, quantity, current_balance,
            )
            deduction_line = overtime_line_model.create(
                slip._prepare_overtime_balance_line_vals(-quantity)
            )
            slip.write({
                "overtime_hours_deducted": quantity,
                "overtime_deduction_line_id": deduction_line.id,
                "overtime_restore_line_id": False,
            })
            _logger.info(
                "Payslip %s overtime deduction line created: line_id=%s manual_duration=%s",
                slip.id, deduction_line.id, deduction_line.manual_duration,
            )

    def _restore_extra_hours_balance(self):
        overtime_line_model = self.env["hr.attendance.overtime.line"].sudo()
        for slip in self:
            if slip.state != "cancel":
                _logger.info("Payslip %s skipped overtime restore: state is %s", slip.id, slip.state)
                continue
            if not slip.overtime_deduction_line_id:
                _logger.info("Payslip %s skipped overtime restore: no deduction line linked", slip.id)
                continue
            if slip.overtime_restore_line_id:
                _logger.info(
                    "Payslip %s skipped overtime restore: already linked to restore line %s",
                    slip.id, slip.overtime_restore_line_id.id,
                )
                continue
            quantity = abs(slip.overtime_deduction_line_id.manual_duration or 0.0) or slip.overtime_hours_deducted
            if quantity <= 0:
                _logger.info("Payslip %s skipped overtime restore: quantity is %s", slip.id, quantity)
                continue
            _logger.info(
                "Payslip %s overtime restore start: employee=%s quantity=%s deduction_line=%s",
                slip.id, slip.employee_id.id, quantity, slip.overtime_deduction_line_id.id,
            )
            restore_line = overtime_line_model.create(
                slip._prepare_overtime_balance_line_vals(quantity)
            )
            slip.write({
                "overtime_hours_deducted": 0.0,
                "overtime_restore_line_id": restore_line.id,
                "overtime_deduction_line_id": False,
            })
            _logger.info(
                "Payslip %s overtime restore line created: line_id=%s manual_duration=%s",
                slip.id, restore_line.id, restore_line.manual_duration,
            )

    def action_payslip_done(self):
        self._apply_termination_clearance_inputs()
        self._deduct_extra_hours_balance()
        return super().action_payslip_done()

    def action_payslip_cancel(self):
        res = super().action_payslip_cancel()
        self._restore_extra_hours_balance()
        return res
