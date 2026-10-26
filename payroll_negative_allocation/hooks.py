# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Safely drop the duration check constraint without causing lock timeouts."""
    env.cr.execute("""
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'hr_leave_allocation_duration_check'
    """)
    if env.cr.fetchone():
        try:
            env.cr.execute("ALTER TABLE hr_leave_allocation DROP CONSTRAINT IF EXISTS hr_leave_allocation_duration_check;")
            _logger.info("[payroll_negative_allocation] Successfully dropped hr_leave_allocation_duration_check constraint.")
        except Exception as e:
            _logger.warning("[payroll_negative_allocation] Could not drop constraint immediately: %s", e)
