# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    _sql_constraints = [
        ('duration_check', 'CHECK(1=1)', 'The duration must be valid.'),
    ]

    def _auto_init(self):
        # Ensure the constraint exists in PostgreSQL as CHECK(1=1) before Odoo's _add_sql_constraints() runs.
        # When hr_leave_allocation_duration_check exists, Odoo's ORM skips adding the strict >= 0 constraint.
        try:
            self.env.cr.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint 
                        WHERE conname = 'hr_leave_allocation_duration_check'
                          AND pg_get_constraintdef(oid) LIKE '%1 = 1%'
                    ) THEN
                        ALTER TABLE hr_leave_allocation DROP CONSTRAINT IF EXISTS hr_leave_allocation_duration_check;
                        ALTER TABLE hr_leave_allocation ADD CONSTRAINT hr_leave_allocation_duration_check CHECK (1 = 1);
                    END IF;
                END $$;
            """)
            _logger.info("[payslip_format_view] hr_leave_allocation_duration_check ensured as CHECK(1=1).")
        except Exception as e:
            _logger.warning("[payslip_format_view] Constraint adjustment deferred: %s", e)
        return super()._auto_init()

    @api.constrains('number_of_days', 'number_of_days_display')
    def _check_duration(self):
        """Allow negative leave allocations without validation error."""
        return True
