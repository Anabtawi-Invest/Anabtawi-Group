from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_expense_limit = fields.Float(related="pos_config_id.expense_limit", readonly=False)
    pos_expense_pending_amount = fields.Float(related="pos_config_id.expense_pending_amount")
    pos_expense_available_amount = fields.Float(related="pos_config_id.expense_available_amount")
