import logging

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def _attendance_action_change(self, geo_information=None):
        """Block check-in when current extra hours exceed the configured limit."""
        self.ensure_one()

        is_check_in = self.attendance_state != "checked_in"
        _logger.info(
            (
                "[planning_enhancement][checkin_guard] source=hr_employee._attendance_action_change "
                "employee_id=%s employee=%s attendance_state=%s is_check_in=%s "
                "total_overtime=%.2f max_allowed=%.2f"
            ),
            self.id,
            self.display_name,
            self.attendance_state,
            is_check_in,
            self.total_overtime or 0.0,
            self.company_id.planning_max_extra_hours or 0.0,
        )
        if is_check_in:
            max_extra_hours = self.company_id.planning_max_extra_hours or 0.0
            current_extra_hours = self.total_overtime or 0.0
            if max_extra_hours > 0 and current_extra_hours > max_extra_hours + 1e-6:
                _logger.warning(
                    (
                        "[planning_enhancement][checkin_guard] blocked=True employee_id=%s "
                        "current_extra_hours=%.2f max_extra_hours=%.2f"
                    ),
                    self.id,
                    current_extra_hours,
                    max_extra_hours,
                )
                raise UserError(
                    _(
                        "Cannot check in %(employee)s because current Extra Hours (%(current).2f) exceed the configured maximum (%(maximum).2f). "
                        "Please convert some hours to Time Off first."
                    )
                    % {
                        "employee": self.display_name,
                        "current": current_extra_hours,
                        "maximum": max_extra_hours,
                    }
                )
            _logger.info(
                (
                    "[planning_enhancement][checkin_guard] blocked=False employee_id=%s "
                    "reason=within_limit_or_limit_disabled"
                ),
                self.id,
            )
        return super()._attendance_action_change(geo_information=geo_information)
