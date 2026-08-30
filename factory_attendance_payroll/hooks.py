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
    Salary rules are defined in data/hr_payroll_data.xml.
    """
    pass
