# -*- coding: utf-8 -*-
"""Drop strict leave allocation duration check before schema sync.

Negative allocations are intentional (payroll_fix_recon / payroll_negative_allocation).
Odoo core wants CHECK(number_of_days >= 0); recreating that during -u fails the build.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        "ALTER TABLE hr_leave_allocation "
        "DROP CONSTRAINT IF EXISTS hr_leave_allocation_duration_check"
    )
    _logger.info(
        "[payroll_fix_recon] pre-migrate 19.0.1.4.8: dropped "
        "hr_leave_allocation_duration_check if present"
    )
