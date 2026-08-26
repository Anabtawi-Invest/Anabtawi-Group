# -*- coding: utf-8 -*-
from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    enable_overtime_calculation = fields.Boolean(
        string="Enable Overtime Calculation",
        default=True,
        help="When unchecked, extra hours worked beyond the schedule are treated as unpaid hours and will not generate overtime or affect payslips."
    )

    def _auto_init(self):
        try:
            self.env.cr.execute("""
                ALTER TABLE res_company 
                ADD COLUMN IF NOT EXISTS enable_overtime_calculation BOOLEAN DEFAULT TRUE;
            """)
        except Exception:
            pass
        return super()._auto_init()
