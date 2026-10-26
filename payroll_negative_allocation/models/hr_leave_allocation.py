# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    def init(self):
        super().init()
        # Safe non-blocking check in Postgres system catalog (takes no lock on hr_leave_allocation)
        self.env.cr.execute("""
            SELECT 1 FROM pg_constraint 
            WHERE conname = 'hr_leave_allocation_duration_check'
        """)
        if self.env.cr.fetchone():
            try:
                self.env.cr.execute("ALTER TABLE hr_leave_allocation DROP CONSTRAINT IF EXISTS hr_leave_allocation_duration_check;")
            except Exception as e:
                _logger.warning("[payroll_negative_allocation] Deferred dropping constraint to post_init_hook: %s", e)

    @api.constrains('number_of_days', 'number_of_days_display')
    def _check_duration(self):
        """Override Odoo default duration constraint to allow negative leave allocations."""
        # Allow negative allocations for balance adjustments and payroll recon deductions
        return True
