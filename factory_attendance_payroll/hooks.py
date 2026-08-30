# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID


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


def post_init_hook(env):
    """
    Post-Init Hook:
    Binds attendance reconciliation rules (ATT_RECON_VAR, OT_NET, DED_UNDERTIME)
    dynamically to all Payroll Structures in the database.
    """
    try:
        structures = env['hr.payroll.structure'].sudo().search([])
        rules = env['hr.salary.rule'].sudo().search([('code', 'in', ['ATT_RECON_VAR', 'OT_NET', 'DED_UNDERTIME'])])

        for structure in structures:
            for rule in rules:
                existing = env['hr.salary.rule'].sudo().search([
                    ('code', '=', rule.code),
                    ('struct_id', '=', structure.id)
                ], limit=1)
                if not existing:
                    rule.sudo().copy({'struct_id': structure.id})
    except Exception:
        pass
