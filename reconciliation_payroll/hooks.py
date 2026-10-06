# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """
    Post-Init Hook:
    1. Associates reconciliation salary rules with all existing salary structures.
    2. Ensures work entry types have valid rounding parameters to avoid Odoo 19 validation crashes.
    3. Sets allow_annual_leave_lateness_deduction to True for employees.
    """
    # 1. Link salary rules to payroll structures
    try:
        rules = env['hr.salary.rule'].sudo().search([
            ('code', 'in', ['ATT_RECON_VAR', 'OT_NET', 'DED_UNDERTIME', 'ACTUAL'])
        ])
        structures = env['hr.payroll.structure'].sudo().search([])
        if rules and structures:
            for rule in rules:
                if hasattr(structures, 'rule_ids'):
                    structures.write({'rule_ids': [(4, rule.id)]})
        _logger.info("[reconciliation_payroll] Successfully linked salary rules to structures.")
    except Exception:
        _logger.exception("[reconciliation_payroll] Error linking salary rules to structures.")

    # 2. Fix work entry types rounding
    try:
        bad_types = env['hr.work.entry.type'].sudo().search([
            ('round_days', 'in', ['HALF', 'FULL']),
            ('round_days_type', '=', False),
        ])
        if bad_types:
            bad_types.write({'round_days_type': 'DOWN'})

        no_round_types = env['hr.work.entry.type'].sudo().search([
            ('round_days', '=', False),
        ])
        if no_round_types:
            no_round_types.write({'round_days': 'NO', 'round_days_type': 'DOWN'})
    except Exception:
        _logger.exception("[reconciliation_payroll] Error fixing work entry types rounding.")

    # 3. Default allow_annual_leave_lateness_deduction to True
    try:
        employees = env['hr.employee'].sudo().search([
            ('allow_annual_leave_lateness_deduction', '!=', True)
        ])
        if employees:
            employees.write({'allow_annual_leave_lateness_deduction': True})
    except Exception:
        pass
