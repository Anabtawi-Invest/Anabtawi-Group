# -*- coding: utf-8 -*-
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def pre_init_hook(env):
    """
    Pre-Init Hook (Runs before XML data loading):
    Safely ensures all required PostgreSQL columns exist.
    """
    with env.cr.savepoint():
        try:
            env.cr.execute("""
                ALTER TABLE res_company 
                ADD COLUMN IF NOT EXISTS enable_overtime_calculation BOOLEAN DEFAULT TRUE;
            """)
        except Exception:
            pass

    with env.cr.savepoint():
        try:
            env.cr.execute("""
                ALTER TABLE hr_attendance 
                ADD COLUMN IF NOT EXISTS daily_undertime_hours DOUBLE PRECISION DEFAULT 0.0,
                ADD COLUMN IF NOT EXISTS daily_overtime_hours DOUBLE PRECISION DEFAULT 0.0;
            """)
        except Exception:
            pass

    with env.cr.savepoint():
        try:
            env.cr.execute("""
                ALTER TABLE hr_payslip 
                ADD COLUMN IF NOT EXISTS remaining_extra_hours_balance DOUBLE PRECISION DEFAULT 0.0;
            """)
        except Exception:
            pass

    with env.cr.savepoint():
        try:
            env.cr.execute("""
                UPDATE hr_work_entry_type
                   SET round_days_type = 'DOWN'
                 WHERE round_days IN ('HALF', 'FULL')
                   AND (round_days_type IS NULL OR round_days_type = '');
            """)
            if env.cr.rowcount:
                _logger.warning(
                    "[factory_attendance_payroll] pre_init_hook fixed %s work entry type(s) "
                    "with missing round_days_type via SQL.",
                    env.cr.rowcount,
                )
        except Exception:
            _logger.exception(
                "[factory_attendance_payroll] pre_init_hook failed to fix round_days_type via SQL."
            )


def _fix_work_entry_type_rounding(env):
    """Ensure rounding-enabled work entry types always have a round type."""
    bad_types = env['hr.work.entry.type'].sudo().search([
        ('round_days', '!=', 'NO'),
        ('round_days_type', '=', False),
    ])
    if bad_types:
        _logger.warning(
            "[factory_attendance_payroll] Fixing %s work entry type(s) with round_days enabled "
            "but missing round_days_type: %s",
            len(bad_types),
            [(t.id, t.name, t.code, t.round_days, t.round_days_type) for t in bad_types],
        )
        bad_types.write({'round_days_type': 'DOWN'})

    absent_type = env.ref(
        'factory_attendance_payroll.work_entry_type_absent',
        raise_if_not_found=False,
    )
    if absent_type and (not absent_type.round_days_type or absent_type.round_days != 'NO'):
        absent_type.write({'round_days': 'NO', 'round_days_type': 'DOWN'})


def post_init_hook(env):
    """
    Post-Init Hook:
    Links created reconciliation salary rules to all salary structures.
    """
    try:
        rules = env['hr.salary.rule'].sudo().search([
            ('code', 'in', ['ATT_RECON_VAR', 'OT_NET', 'DED_UNDERTIME'])
        ])
        structures = env['hr.payroll.structure'].sudo().search([])
        if rules and structures:
            for rule in rules:
                if hasattr(structures, 'rule_ids'):
                    structures.write({'rule_ids': [(4, rule.id)]})
    except Exception:
        pass

    try:
        _fix_work_entry_type_rounding(env)
    except Exception:
        pass
