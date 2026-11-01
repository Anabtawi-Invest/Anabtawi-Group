# -*- coding: utf-8 -*-
import logging

from odoo.exceptions import UserError

from .models.pfr_utils import OLD_MODULES

_logger = logging.getLogger(__name__)

BACKUP_TABLE = 'pfr_employee_backup'


def pre_init_hook(env):
    """payroll_fix_recon replaces the legacy modules: it re-declares the same models, fields and salary
    rule codes, so running both would double-process every payslip."""
    old = env['ir.module.module'].sudo().search([
        ('name', 'in', list(OLD_MODULES)), ('state', 'in', ('installed', 'to upgrade', 'to install'))])
    if old:
        _logger.warning(
            "[payroll_fix_recon] Replacing legacy module(s) %s: deactivating them safely.",
            ', '.join(old.mapped('name')))
        old.write({'state': 'uninstalled'})


def post_init_hook(env):
    # Work Injury days are paid at 7.5% of the daily wage
    injury = env['hr.work.entry.type'].sudo().search([('name', 'ilike', 'work injury'), ('pfr_pay_percent', '=', 100.0)])
    injury.write({'pfr_pay_percent': 7.5})

    env.cr.execute("SELECT to_regclass(%s)", (BACKUP_TABLE,))
    if env.cr.fetchone()[0]:
        env.cr.execute("""
            UPDATE hr_employee e
               SET employee_work_station = b.employee_work_station,
                   break_duration_hours = b.break_duration_hours,
                   allow_annual_leave_lateness_deduction = b.allow_annual_leave_lateness_deduction
              FROM %s b WHERE b.id = e.id
        """ % BACKUP_TABLE)
        _logger.info("[payroll_fix_recon] restored %s employee settings from %s", env.cr.rowcount, BACKUP_TABLE)
        env.invalidate_all()
