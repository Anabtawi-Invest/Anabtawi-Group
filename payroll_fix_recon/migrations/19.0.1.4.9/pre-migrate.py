# -*- coding: utf-8 -*-
"""Drop strict leave allocation duration check before schema sync.

Negative allocations are intentional. After this drop, Odoo 19 recreates
hr_leave_allocation_duration_check from payroll_fix_recon's models.Constraint
override (CHECK(1=1)), not core's number_of_days >= 0.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        "ALTER TABLE hr_leave_allocation "
        "DROP CONSTRAINT IF EXISTS hr_leave_allocation_duration_check"
    )
    _logger.info(
        "[payroll_fix_recon] pre-migrate 19.0.1.4.9: dropped "
        "hr_leave_allocation_duration_check if present"
    )
