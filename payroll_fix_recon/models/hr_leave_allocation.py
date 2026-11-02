# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    # Odoo 19 ignores _sql_constraints. This replaces hr_leave_allocation_duration_check
    # (CHECK number_of_days >= 0). CHECK (1=1) can be installed even when rows are negative.
    _duration_check = models.Constraint(
        "CHECK (1=1)",
        "The duration must be valid.",
    )

    def _auto_init(self):
        try:
            self.env.cr.execute("""
                SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conname = 'hr_leave_allocation_duration_check'
            """)
            row = self.env.cr.fetchone()
            if row and '1=1' not in (row[0] or '').replace(' ', ''):
                self.env.cr.execute(
                    "ALTER TABLE hr_leave_allocation DROP CONSTRAINT IF EXISTS hr_leave_allocation_duration_check"
                )
                _logger.info("[payroll_fix_recon] Dropped legacy hr_leave_allocation_duration_check.")
        except Exception as e:
            _logger.warning("[payroll_fix_recon] Constraint drop deferred: %s", e)
        return super()._auto_init()

    @api.constrains('number_of_days', 'number_of_days_display')
    def _check_duration(self):
        """Override Odoo default duration constraint to allow negative leave allocations."""
        return True
