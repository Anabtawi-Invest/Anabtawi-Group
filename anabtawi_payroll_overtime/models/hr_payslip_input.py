from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_OVER_BALANCE_EPS = 1e-6


class HrPayslipInput(models.Model):
    _inherit = "hr.payslip.input"
    _OVERTIME_FIXED_HOURS = 48.0

    quantity = fields.Float(
        string="Quantity",
        digits=(16, 2),
        help="Overtime hours to convert to amount.",
    )
    overtime_quantity_type = fields.Boolean(
        related="input_type_id.overtime_quantity_type",
        string="Overtime Quantity Type",
        readonly=True,
    )

    @api.constrains("quantity", "input_type_id", "payslip_id")
    def _check_overtime_quantity_extra_hours_balance(self):
        """Block saving payslip inputs that would pay more extra hours than the balance."""
        for slip in self.mapped("payslip_id").filtered(lambda s: s and s.state != "cancel"):
            total_qty = slip._get_overtime_quantity_to_deduct()
            if total_qty <= _OVER_BALANCE_EPS:
                continue
            balance = slip._get_employee_extra_hours_balance()
            if total_qty > balance + _OVER_BALANCE_EPS:
                raise ValidationError(slip._message_overtime_exceeds_balance(total_qty, balance))

    @api.onchange("quantity", "input_type_id", "payslip_id")
    def _onchange_overtime_quantity_amount(self):
        self._apply_overtime_quantity_amount()
        if not self.overtime_quantity_type or not self.payslip_id:
            return
        total_qty = self.payslip_id._get_overtime_quantity_to_deduct()
        balance = self.payslip_id._get_employee_extra_hours_balance()
        if total_qty > balance + _OVER_BALANCE_EPS:
            return {
                "warning": {
                    "title": _("Insufficient extra hours balance"),
                    "message": self.payslip_id._message_overtime_exceeds_balance(total_qty, balance),
                }
            }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._apply_overtime_quantity_amount()
        return records

    def write(self, vals):
        res = super().write(vals)
        if any(field in vals for field in ("quantity", "input_type_id", "payslip_id")):
            self._apply_overtime_quantity_amount()
        return res

    def _apply_overtime_quantity_amount(self):
        for line in self:
            if not line.overtime_quantity_type:
                continue
            line.amount = line.quantity * line._get_employee_hourly_rate()

    def _get_employee_hourly_rate(self):
        self.ensure_one()
        payslip = self.payslip_id
        version = payslip.version_id
        if not version:
            return 0.0
        if payslip.wage_type == "hourly":
            return version.hourly_wage
        return version.contract_wage / self._OVERTIME_FIXED_HOURS
