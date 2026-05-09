from datetime import datetime, timedelta
import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

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
            slip.employee_extra_hours_balance = slip._get_employee_extra_hours_balance()

    def _get_employee_extra_hours_balance(self):
        self.ensure_one()
        if not self.employee_id:
            return 0.0
        # Align with OT wallet when latness_deduction (or similar) is installed.
        if hasattr(self, "_get_ot_available_for_deduction"):
            return max(0.0, self._get_ot_available_for_deduction())

        if hasattr(self.employee_id, "get_overtime_data_by_employee"):
            overtime_data = self.employee_id.get_overtime_data_by_employee()
            return max(0.0, overtime_data.get(self.employee_id.id, {}).get("unspent_compensable_overtime", 0.0))
        return 0.0

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
        self._deduct_extra_hours_balance()
        return super().action_payslip_done()

    def action_payslip_cancel(self):
        res = super().action_payslip_cancel()
        self._restore_extra_hours_balance()
        return res
