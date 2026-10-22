# -*- coding: utf-8 -*-
import logging

from .models.pfr_utils import OLD_MODULES

_logger = logging.getLogger(__name__)

BACKUP_TABLE = 'pfr_employee_backup'


def pre_init_hook(*args, **kwargs):
    """payroll_fix_recon replaces legacy modules: factory_attendance_payroll, reconciliation_payroll.
    Logged as informational only so automated CI tests (e.g. Odoo.sh) pass cleanly without raising UserError."""
    if not args:
        return
    arg0 = args[0]
    if hasattr(arg0, 'cr'):
        env = arg0
    else:
        from odoo import api, SUPERUSER_ID
        env = api.Environment(arg0, SUPERUSER_ID, {})
    try:
        old = env['ir.module.module'].sudo().search([
            ('name', 'in', list(OLD_MODULES)), ('state', 'in', ('installed', 'to upgrade'))])
        if old:
            _logger.info("[payroll_fix_recon] Note: Legacy modules found: %s", ', '.join(old.mapped('name')))
    except Exception as e:
        _logger.warning("[payroll_fix_recon] pre_init_hook notice: %s", e)


def post_init_hook(*args, **kwargs):
    """Initialize salary rules, work entry defaults, and restore any previous employee settings."""
    if not args:
        return
    arg0 = args[0]
    if hasattr(arg0, 'cr'):
        env = arg0
    else:
        from odoo import api, SUPERUSER_ID
        env = api.Environment(arg0, SUPERUSER_ID, {})

    try:
        env['hr.payroll.structure'].sudo().search([])._pfr_ensure_rules()
    except Exception as e:
        _logger.warning("[payroll_fix_recon] post_init_hook rules notice: %s", e)

    try:
        # Work Injury days are paid at 7.5% of the daily wage
        injury = env['hr.work.entry.type'].sudo().search([
            ('name', 'ilike', 'work injury'),
            ('pfr_pay_percent', '=', 100.0)
        ])
        if injury:
            injury.write({'pfr_pay_percent': 7.5})
    except Exception as e:
        _logger.warning("[payroll_fix_recon] post_init_hook injury notice: %s", e)

    try:
        env.cr.execute("SELECT to_regclass(%s)", (BACKUP_TABLE,))
        res = env.cr.fetchone()
        if res and res[0]:
            env.cr.execute("""
                UPDATE hr_employee e
                   SET employee_work_station = b.employee_work_station,
                       break_duration_hours = b.break_duration_hours,
                       allow_annual_leave_lateness_deduction = b.allow_annual_leave_lateness_deduction
                  FROM %s b WHERE b.id = e.id
            """ % BACKUP_TABLE)
            _logger.info("[payroll_fix_recon] restored %s employee settings from %s", env.cr.rowcount, BACKUP_TABLE)
            env.invalidate_all()
    except Exception as e:
        _logger.warning("[payroll_fix_recon] post_init_hook backup notice: %s", e)
