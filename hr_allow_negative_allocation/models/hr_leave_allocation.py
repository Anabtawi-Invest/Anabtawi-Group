# -*- coding: utf-8 -*-
from odoo import models


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    def init(self):
        super().init()
        # Safe non-blocking check in Postgres catalog (takes no lock on hr_leave_allocation)
        self.env.cr.execute("""
            SELECT 1 FROM pg_constraint 
            WHERE conname = 'hr_leave_allocation_duration_check'
        """)
        if self.env.cr.fetchone():
            # Only execute ALTER TABLE if the constraint still actually exists
            self.env.cr.execute("ALTER TABLE hr_leave_allocation DROP CONSTRAINT IF EXISTS hr_leave_allocation_duration_check;")
