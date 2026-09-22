# -*- coding: utf-8 -*-
from odoo import models


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    def unlink(self):
        """
        Fast bulk-delete path used before Excel recreate.

        Must skip:
        - core overtime rebuild
        - enterprise work-entry regeneration (can raise
          "Duration must be positive and cannot exceed 24 hours")
        """
        if self.env.context.get("hr_attendance_excel_bulk_delete"):
            self._excel_bulk_detach_work_entries()
            # Bypass all hr.attendance unlink overrides; @api.ondelete still runs,
            # so validated work entries must already be drafted by the delete job.
            return models.Model.unlink(self)
        return super().unlink()

    def _excel_bulk_detach_work_entries(self):
        """Detach/archive linked work entries without regenerating them."""
        if not self or "hr.work.entry" not in self.env:
            return
        # Clear links + archive draft/conflict entries for these attendances/days.
        # Avoid ORM writes that may re-validate duration.
        self.env.cr.execute(
            """
            UPDATE hr_work_entry
               SET attendance_id = NULL,
                   active = FALSE
             WHERE attendance_id = ANY(%s)
                OR (
                    employee_id = ANY(%s)
                    AND date = ANY(%s)
                    AND state IN ('draft', 'conflict')
                )
            """,
            [
                list(self.ids),
                list(self.employee_id.ids),
                list(self.mapped("date")),
            ],
        )
        self.env["hr.work.entry"].invalidate_model()
