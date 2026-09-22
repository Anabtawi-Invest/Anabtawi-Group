# -*- coding: utf-8 -*-
from odoo import models


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    def unlink(self):
        # Fast path for mass delete before Excel recreate: skip per-record overtime rebuild.
        if self.env.context.get("hr_attendance_excel_bulk_delete"):
            return models.Model.unlink(self)
        return super().unlink()
