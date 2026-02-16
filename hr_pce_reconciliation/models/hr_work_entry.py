# -*- coding: utf-8 -*-
from odoo import fields, models

class HrWorkEntry(models.Model):
    _inherit = "hr.work.entry"

    pce_reconciled = fields.Boolean(string="PCE Reconciled", default=False, copy=False)
    pce_reconciled_payslip_id = fields.Many2one("hr.payslip", string="Reconciled Payslip", copy=False)
