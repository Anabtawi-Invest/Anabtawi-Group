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
        _logger.warning(
            "[anabtawi_payroll_overtime] create hr.payslip.input ids=%s vals_list=%s",
            records.ids,
            vals_list,
        )
        records._apply_overtime_quantity_amount()
        return records

    def write(self, vals):
        res = super().write(vals)
        _logger.warning(
            "[anabtawi_payroll_overtime] write hr.payslip.input ids=%s vals=%s",
            self.ids,
            vals,
        )
        if any(field in vals for field in ("quantity", "input_type_id", "payslip_id")):
            self._apply_overtime_quantity_amount()
        return res

    def _apply_overtime_quantity_amount(self):
        for line in self:
            if line.input_type_id.code == "REM_LEAVE":
                rate = line._get_rem_leave_hourly_rate()
                new_amount = line.quantity * rate
                _logger.warning(
                    "[anabtawi_payroll_overtime] REM_LEAVE amount compute line_id=%s payslip_id=%s quantity=%s rate=%s old_amount=%s new_amount=%s",
                    line.id,
                    line.payslip_id.id,
                    line.quantity,
                    rate,
                    line.amount,
                    new_amount,
                )
                line.amount = new_amount
                continue
            if line.overtime_quantity_type:
                rate = line._get_employee_hourly_rate()
                new_amount = line.quantity * rate
                _logger.warning(
                    "[anabtawi_payroll_overtime] overtime amount compute line_id=%s code=%s payslip_id=%s quantity=%s rate=%s old_amount=%s new_amount=%s",
                    line.id,
                    line.input_type_id.code,
                    line.payslip_id.id,
                    line.quantity,
                    rate,
                    line.amount,
                    new_amount,
                )
                line.amount = new_amount

    def _get_employee_hourly_rate(self):
        self.ensure_one()
        payslip = self.payslip_id
        version = payslip.version_id
        if not version:
            return 0.0
        if payslip.wage_type == "hourly":
            return version.hourly_wage
        return version.contract_wage / self._OVERTIME_FIXED_HOURS

    def _get_rem_leave_hourly_rate(self):
        self.ensure_one()
        payslip = self.payslip_id
        if not payslip:
            _logger.warning(
                "[anabtawi_payroll_overtime] REM_LEAVE rate: no payslip on line_id=%s",
                self.id,
            )
            return 0.0
        wage = 0.0
        wage_source = "none"
        if "wage" in payslip._fields:
            wage = payslip.wage or 0.0
            if wage:
                wage_source = "payslip.wage"
        if not wage and payslip.employee_id and "wage" in payslip.employee_id._fields:
            wage = payslip.employee_id.wage or 0.0
            if wage:
                wage_source = "employee.wage"
        if not wage and payslip.contract_id:
            wage = payslip.contract_id.wage or 0.0
            if wage:
                wage_source = "contract.wage"
        if not wage and "version_id" in payslip._fields and payslip.version_id:
            wage = payslip.version_id.contract_wage or 0.0
            if wage:
                wage_source = "version.contract_wage"
        rate = wage / (8.0 * 30.0)
        _logger.warning(
            "[anabtawi_payroll_overtime] REM_LEAVE rate details line_id=%s payslip_id=%s wage_source=%s wage=%s rate=%s quantity=%s input_code=%s",
            self.id,
            payslip.id,
            wage_source,
            wage,
            rate,
            self.quantity,
            self.input_type_id.code,
        )
        return rate
