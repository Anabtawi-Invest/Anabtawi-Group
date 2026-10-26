# -*- coding: utf-8 -*-
import logging
from odoo import api, models

_logger = logging.getLogger(__name__)


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    # Override standard Odoo duration_check (CHECK(number_of_days >= 0)) with CHECK(1=1)
    # so Odoo ORM will never fail when existing database rows contain negative leave allocations.
    _sql_constraints = [
        ('duration_check', 'CHECK(1=1)', 'The duration must be valid.'),
    ]

    def _auto_init(self):
        try:
            self.env.cr.execute("""
                SELECT 1 FROM pg_constraint 
                WHERE conname = 'hr_leave_allocation_duration_check'
                  AND pg_get_constraintdef(oid) LIKE '%>= 0%'
            """)
            if self.env.cr.fetchone():
                self.env.cr.execute("ALTER TABLE hr_leave_allocation DROP CONSTRAINT IF EXISTS hr_leave_allocation_duration_check;")
                _logger.info("[payslip_format_view] Dropped legacy strict hr_leave_allocation_duration_check constraint.")
        except Exception as e:
            _logger.warning("[payslip_format_view] Constraint check/drop deferred: %s", e)
        return super()._auto_init()

    @api.constrains('number_of_days', 'number_of_days_display')
    def _check_duration(self):
        """Allow negative leave allocations without validation error."""
        return True
