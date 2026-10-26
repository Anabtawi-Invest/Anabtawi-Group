# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    # Override standard Odoo duration_check (CHECK(number_of_days >= 0)) with CHECK(1=1)
    # so Odoo ORM will never try to enforce positive duration on existing negative rows.
    _sql_constraints = [
        ('duration_check', 'CHECK(1=1)', 'The duration must be valid.'),
    ]

    def _auto_init(self):
        # Drop the strict >= 0 constraint if it exists before Odoo validates it
        try:
            self.env.cr.execute("""
                SELECT 1 FROM pg_constraint 
                WHERE conname = 'hr_leave_allocation_duration_check'
                  AND pg_get_constraintdef(oid) LIKE '%>= 0%'
            """)
            if self.env.cr.fetchone():
                self.env.cr.execute("ALTER TABLE hr_leave_allocation DROP CONSTRAINT IF EXISTS hr_leave_allocation_duration_check;")
                _logger.info("[payroll_fix_recon] Dropped legacy strict hr_leave_allocation_duration_check constraint.")
        except Exception as e:
            _logger.warning("[payroll_fix_recon] Constraint drop deferred: %s", e)
        return super()._auto_init()

    @api.constrains('number_of_days', 'number_of_days_display')
    def _check_duration(self):
        """Override Odoo default duration constraint to allow negative leave allocations."""
        return True
