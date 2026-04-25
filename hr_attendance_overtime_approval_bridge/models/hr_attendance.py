# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    @api.depends("check_in", "check_out", "employee_id")
    def _compute_overtime_status(self):
        for attendance in self:
            linked_overtimes = attendance.linked_overtime_ids
            if not linked_overtimes:
                attendance.overtime_status = False
            elif any(linked_overtimes.mapped(lambda ot: ot.status == "to_approve")):
                attendance.overtime_status = "to_approve"
            elif any(linked_overtimes.mapped(lambda ot: ot.status == "approved")):
                attendance.overtime_status = "approved"
            else:
                attendance.overtime_status = "refused"
