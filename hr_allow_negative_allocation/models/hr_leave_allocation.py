# -*- coding: utf-8 -*-
from odoo import models

class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    _duration_check = models.Constraint(
        'CHECK(true)',
        'Duration constraint bypassed for opening balances'
    )

    def init(self):
        super().init()
        self.env.cr.execute("ALTER TABLE hr_leave_allocation DROP CONSTRAINT IF EXISTS hr_leave_allocation_duration_check;")
