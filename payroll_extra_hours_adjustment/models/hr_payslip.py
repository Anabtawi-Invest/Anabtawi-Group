from datetime import datetime, timedelta

from odoo import _, fields, models
from odoo.exceptions import ValidationError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    manual_extra_hours_balance = fields.Float(
        string="Additional Extra Hours Balance",
        help="Manual additional extra hours to add to the employee balance.",
    )

    def _prepare_manual_extra_hours_line_vals(self, adjustment_hours):
        self.ensure_one()
        date_value = self.date_to or fields.Date.context_today(self)
        date_dt = datetime.combine(date_value, datetime.min.time())
        return {
            "employee_id": self.employee_id.id,
            "date": date_value,
            "duration": adjustment_hours,
            "manual_duration": adjustment_hours,
            "time_start": date_dt,
            "time_stop": date_dt + timedelta(minutes=1),
            "amount_rate": 1.0,
            "status": "approved",
            "compensable_as_leave": True,
        }

    def action_apply_additional_extra_hours(self):
        self.ensure_one()
        if not self.employee_id:
            raise ValidationError(_("Please select an employee before applying additional extra hours."))
        if self.manual_extra_hours_balance <= 0:
            raise ValidationError(_("Additional extra hours value must be greater than zero."))

        adjustment_hours = self.manual_extra_hours_balance
        overtime_line = self.env["hr.attendance.overtime.line"].sudo()
        overtime_line.create(self._prepare_manual_extra_hours_line_vals(adjustment_hours))

        self.manual_extra_hours_balance = 0.0
        if "employee_extra_hours_balance" in self._fields and hasattr(self, "_compute_employee_extra_hours_balance"):
            self._compute_employee_extra_hours_balance()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": _("Additional extra hours have been applied successfully."),
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }
