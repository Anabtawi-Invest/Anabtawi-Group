from datetime import datetime, timedelta
import logging

from odoo import _, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    manual_extra_hours_balance = fields.Float(
        string="Additional Extra Hours Balance",
        help="Manual additional extra hours to add to the employee balance.",
    )
    additional_extra_hours_line_id = fields.Many2one(
        "hr.attendance.overtime.line",
        string="Additional Extra Hours Entry",
        readonly=True,
        copy=False,
        help="Overtime entry created from the Apply Additional Extra Hours action.",
    )
    additional_extra_hours_reversal_line_id = fields.Many2one(
        "hr.attendance.overtime.line",
        string="Additional Extra Hours Reversal Entry",
        readonly=True,
        copy=False,
        help="Overtime entry created to reverse the additional extra hours.",
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
        if self.additional_extra_hours_line_id and not self.additional_extra_hours_reversal_line_id:
            raise ValidationError(
                _(
                    "You already applied additional extra hours on this payslip. "
                    "Please reset/cancel it first before applying another value."
                )
            )

        adjustment_hours = self.manual_extra_hours_balance
        overtime_line = self.env["hr.attendance.overtime.line"].sudo()
        balance_before = self.employee_extra_hours_balance if "employee_extra_hours_balance" in self._fields else None
        _logger.info(
            "Apply additional extra hours started: payslip=%s employee=%s added_hours=%s balance_before=%s",
            self.id, self.employee_id.id, adjustment_hours, balance_before,
        )
        created_line = overtime_line.create(self._prepare_manual_extra_hours_line_vals(adjustment_hours))
        _logger.info(
            "Manual overtime line created from payslip: payslip=%s line_id=%s manual_duration=%s status=%s compensable=%s",
            self.id,
            created_line.id,
            created_line.manual_duration,
            created_line.status,
            created_line.compensable_as_leave,
        )

        self.write({
            "manual_extra_hours_balance": 0.0,
            "additional_extra_hours_line_id": created_line.id,
            "additional_extra_hours_reversal_line_id": False,
        })
        if "employee_extra_hours_balance" in self._fields and hasattr(self, "_compute_employee_extra_hours_balance"):
            self._compute_employee_extra_hours_balance()
            _logger.info(
                "Apply additional extra hours finished: payslip=%s employee=%s balance_after=%s",
                self.id, self.employee_id.id, self.employee_extra_hours_balance,
            )

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

    def action_reset_additional_extra_hours(self):
        self.ensure_one()
        if not self.employee_id:
            raise ValidationError(_("Please select an employee before resetting additional extra hours."))
        if not self.additional_extra_hours_line_id:
            raise ValidationError(_("No additional extra hours entry was found to reset on this payslip."))
        if self.additional_extra_hours_reversal_line_id:
            raise ValidationError(_("Additional extra hours were already reset for this payslip."))

        source_line = self.additional_extra_hours_line_id.sudo().exists()
        if not source_line:
            raise ValidationError(_("The original additional extra hours entry no longer exists."))
        if source_line.employee_id != self.employee_id:
            raise ValidationError(_("Cannot reset because the original entry belongs to a different employee."))

        reset_hours = abs(source_line.manual_duration or 0.0)
        if reset_hours <= 0:
            raise ValidationError(_("Cannot reset because original additional hours value is zero."))

        overtime_line = self.env["hr.attendance.overtime.line"].sudo()
        _logger.info(
            "Reset additional extra hours started: payslip=%s employee=%s original_line=%s reset_hours=%s",
            self.id, self.employee_id.id, source_line.id, reset_hours,
        )
        reversal_line = overtime_line.create(self._prepare_manual_extra_hours_line_vals(-reset_hours))
        self.write({
            "additional_extra_hours_reversal_line_id": reversal_line.id,
            "manual_extra_hours_balance": 0.0,
        })

        if "employee_extra_hours_balance" in self._fields and hasattr(self, "_compute_employee_extra_hours_balance"):
            self._compute_employee_extra_hours_balance()
            _logger.info(
                "Reset additional extra hours finished: payslip=%s employee=%s reversal_line=%s balance_after=%s",
                self.id, self.employee_id.id, reversal_line.id, self.employee_extra_hours_balance,
            )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": _("Additional extra hours have been reset successfully."),
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }
