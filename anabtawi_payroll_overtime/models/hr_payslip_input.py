import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_OVER_BALANCE_EPS = 1e-6
_logger = logging.getLogger(__name__)


class HrPayslipInput(models.Model):
    _inherit = "hr.payslip.input"
    _OVERTIME_FIXED_HOURS = 240

    quantity = fields.Float(
        string="Quantity",
        digits=(16, 2),
        readonly=False,
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
            if line.input_type_id.code == "REM_LEAVE":
                rate = line._get_rem_leave_hourly_rate()
                line.amount = line.quantity * rate
                continue
            if line.overtime_quantity_type:
                rate = line._get_employee_hourly_rate()
                line.amount = line.quantity * rate

    def _get_employee_hourly_rate(self):
        self.ensure_one()
        payslip = self.payslip_id
        if not payslip:
            return 0.0

        # 1. Check if hourly wage contract
        if payslip.wage_type == "hourly":
            if hasattr(payslip, "version_id") and payslip.version_id and payslip.version_id.hourly_wage:
                return payslip.version_id.hourly_wage
            if payslip.contract_id and getattr(payslip.contract_id, "hourly_wage", False):
                return payslip.contract_id.hourly_wage

        # 2. Get monthly wage with fallbacks (Payslip -> Employee -> Contract -> Version)
        wage = 0.0
        if getattr(payslip, "wage", False):
            wage = payslip.wage
        elif payslip.employee_id and getattr(payslip.employee_id, "wage", False):
            wage = payslip.employee_id.wage
        elif payslip.contract_id and getattr(payslip.contract_id, "wage", False):
            wage = payslip.contract_id.wage
        elif hasattr(payslip, "version_id") and payslip.version_id and getattr(payslip.version_id, "contract_wage", False):
            wage = payslip.version_id.contract_wage

        return (wage / self._OVERTIME_FIXED_HOURS) if wage else 0.0

    def _get_rem_leave_hourly_rate(self):
        self.ensure_one()
        payslip = self.payslip_id
        if not payslip:
            return 0.0
        wage = 0.0
        if getattr(payslip, "wage", False):
            wage = payslip.wage
        elif payslip.employee_id and getattr(payslip.employee_id, "wage", False):
            wage = payslip.employee_id.wage
        elif payslip.contract_id and getattr(payslip.contract_id, "wage", False):
            wage = payslip.contract_id.wage
        elif hasattr(payslip, "version_id") and payslip.version_id and getattr(payslip.version_id, "contract_wage", False):
            wage = payslip.version_id.contract_wage
        rate = wage / (8.0 * 30.0) if wage else 0.0
        return rate
