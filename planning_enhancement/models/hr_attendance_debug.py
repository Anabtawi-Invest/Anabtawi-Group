import logging

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HrAttendanceDebug(models.Model):
    _inherit = "hr.attendance"

    def _check_extra_hours_limit_before_create(self, vals_list):
        """Block attendance creation when it effectively performs a check-in over limit."""
        for vals in vals_list:
            employee_id = vals.get("employee_id")
            check_in = vals.get("check_in")
            if not employee_id or not check_in:
                continue

            employee = self.env["hr.employee"].browse(employee_id)
            max_extra_hours = employee.company_id.planning_max_extra_hours or 0.0
            current_extra_hours = employee.total_overtime or 0.0

            is_over_limit = (
                max_extra_hours > 0
                and current_extra_hours > max_extra_hours + 1e-6
            )
            _logger.info(
                (
                    "[planning_enhancement][checkin_guard] source=hr_attendance.create.precheck "
                    "employee_id=%s employee=%s check_in=%s check_out=%s "
                    "total_overtime=%.2f max_allowed=%.2f blocked=%s"
                ),
                employee.id,
                employee.display_name,
                vals.get("check_in"),
                vals.get("check_out"),
                current_extra_hours,
                max_extra_hours,
                is_over_limit,
            )

            if is_over_limit:
                raise UserError(
                    _(
                        "Cannot check in %(employee)s because current Extra Hours (%(current).2f) exceed the configured maximum (%(maximum).2f). "
                        "Please convert some hours to Time Off first."
                    )
                    % {
                        "employee": employee.display_name,
                        "current": current_extra_hours,
                        "maximum": max_extra_hours,
                    }
                )

    @api.model_create_multi
    def create(self, vals_list):
        self._check_extra_hours_limit_before_create(vals_list)
        records = super().create(vals_list)
        for rec in records:
            employee = rec.employee_id
            _logger.info(
                (
                    "[planning_enhancement][checkin_guard] source=hr_attendance.create "
                    "attendance_id=%s employee_id=%s employee=%s check_in=%s check_out=%s "
                    "total_overtime=%.2f max_allowed=%.2f"
                ),
                rec.id,
                employee.id,
                employee.display_name,
                rec.check_in,
                rec.check_out,
                employee.total_overtime or 0.0,
                employee.company_id.planning_max_extra_hours or 0.0,
            )
        return records
