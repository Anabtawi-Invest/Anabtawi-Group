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
            line.amount = line.quantity * line._get_employee_hourly_rate()

    def _get_employee_hourly_rate(self):
        self.ensure_one()
        payslip = self.payslip_id
        version = payslip.version_id
        if not version:
            return 0.0
        if payslip.wage_type == "hourly":
            return version.hourly_wage

        attendance_hours = sum(
            worked_days.number_of_hours
            for worked_days in payslip.worked_days_line_ids
            if not worked_days.work_entry_type_id.is_extra_hours
        )
        if not attendance_hours:
            attendance_hours = payslip.sum_worked_hours or 0.0
        if not attendance_hours:
            calendar_hours = (version.resource_calendar_id.hours_per_week or 0.0) * 52.0 / 12.0
            attendance_hours = calendar_hours
        if not attendance_hours:
            return 0.0
        return version.contract_wage / attendance_hours
