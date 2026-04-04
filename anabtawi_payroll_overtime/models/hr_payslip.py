from datetime import datetime, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


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

    @api.depends("employee_id")
    def _compute_employee_extra_hours_balance(self):
        for slip in self:
            slip.employee_extra_hours_balance = slip._get_employee_extra_hours_balance()

    def _get_employee_extra_hours_balance(self):
        self.ensure_one()
        if not self.employee_id:
            return 0.0

        if hasattr(self.employee_id, "get_overtime_data_by_employee"):
            overtime_data = self.employee_id.get_overtime_data_by_employee()
            return max(0.0, overtime_data.get(self.employee_id.id, {}).get("unspent_compensable_overtime", 0.0))
        return 0.0

    def _get_overtime_quantity_to_deduct(self):
        self.ensure_one()
        return sum(
            self.input_line_ids.filtered("overtime_quantity_type").mapped("quantity")
        )

    def _prepare_overtime_deduction_vals(self, quantity):
        self.ensure_one()
        date_value = self.date_to or fields.Date.context_today(self)
        date_dt = datetime.combine(date_value, datetime.min.time())
        return {
            "employee_id": self.employee_id.id,
            "date": date_value,
            "duration": -quantity,
            "manual_duration": -quantity,
            "time_start": date_dt,
            "time_stop": date_dt + timedelta(minutes=1),
            "amount_rate": 1.0,
            "status": "approved",
            "compensable_as_leave": True,
        }

    def _deduct_extra_hours_balance(self):
        overtime_line_model = self.env["hr.attendance.overtime.line"].sudo()
        for slip in self:
            if slip.overtime_hours_deducted:
                continue
            quantity = slip._get_overtime_quantity_to_deduct()
            if quantity <= 0:
                continue
            current_balance = slip._get_employee_extra_hours_balance()
            if quantity > current_balance:
                raise ValidationError(_(
                    "The overtime quantity (%(quantity).2f) is greater than the employee balance (%(balance).2f) for %(employee)s.",
                    quantity=quantity,
                    balance=current_balance,
                    employee=slip.employee_id.name,
                ))
            overtime_line_model.create(slip._prepare_overtime_deduction_vals(quantity))
            slip.overtime_hours_deducted = quantity

    def action_payslip_done(self):
        self._deduct_extra_hours_balance()
        return super().action_payslip_done()
