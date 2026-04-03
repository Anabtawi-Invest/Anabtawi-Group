from odoo import api, fields, models


class HrPayslipInput(models.Model):
    _inherit = "hr.payslip.input"

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

    @api.onchange("quantity", "input_type_id", "payslip_id")
    def _onchange_overtime_quantity_amount(self):
        self._apply_overtime_quantity_amount()

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
            hourly_amount = line.payslip_id.company_id.overtime_hourly_amount
            line.amount = line.quantity * hourly_amount
