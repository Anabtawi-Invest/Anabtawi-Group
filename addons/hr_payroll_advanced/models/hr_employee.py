from odoo import models, fields, api


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    overtime_bank_hours = fields.Float(
        string="OT Bank (Hours)",
        readonly=True,
        help="Live overtime bank balance used by Smart Ledger Mode",
    )

    overtime_bank_amount = fields.Float(
        string="OT Bank Amount",
        readonly=True,
    )
