# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class PosUnifiedReport(models.TransientModel):
    _name = "pos.unified.report"
    _description = "Unified POS Operations Analysis Report"
    _order = "date desc, id desc"

    name = fields.Char(string="Reference / Description", required=True)
    date = fields.Datetime(string="Date & Time", required=True, index=True)
    config_id = fields.Many2one("pos.config", string="POS Branch", required=True, index=True)
    session_id = fields.Many2one("pos.session", string="Session")
    payment_method_id = fields.Many2one("pos.payment.method", string="Payment Method")

    report_type = fields.Selection([
        ("pos_sales", "POS Sales"),
        ("advance_deposit", "Advance Order Deposit"),
        ("cash_in", "Cash In"),
        ("cash_out", "Cash Out"),
        ("rahen_in", "Pledge Received (Rahen In)"),
        ("rahen_out", "Pledge Returned (Rahen Out)"),
    ], string="Report Type", required=True, index=True)

    amount = fields.Float(string="Amount", digits=(16, 3))
    cash_amount = fields.Float(string="Cash Amount", digits=(16, 3))
    visa_amount = fields.Float(string="Visa / Card Amount", digits=(16, 3))
    employee_debt_amount = fields.Float(string="Employee Debt Amount", digits=(16, 3))
    cash_in_amount = fields.Float(string="Cash In Amount", digits=(16, 3))
    cash_out_amount = fields.Float(string="Cash Out Amount", digits=(16, 3))
    rahen_in_amount = fields.Float(string="Rahen In Amount", digits=(16, 3))
    rahen_out_amount = fields.Float(string="Rahen Out Amount", digits=(16, 3))
    advance_amount = fields.Float(string="Advance Deposit Amount", digits=(16, 3))
    delivery_amount = fields.Float(string="Delivery Amount", digits=(16, 3))
    partner_id = fields.Many2one("res.partner", string="Customer")
    company_id = fields.Many2one("res.company", string="Company", default=lambda self: self.env.company)

    def action_export_excel(self):
        wiz_id = self.env.context.get("active_wizard_id")
        if wiz_id:
            wiz = self.env["pos.unified.report.wizard"].sudo().browse(wiz_id)
            if wiz.exists():
                return wiz.action_export_xlsx()
        wiz = self.env["pos.unified.report.wizard"].sudo().create({})
        return wiz.action_export_xlsx()
