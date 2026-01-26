from odoo import models, fields

class PosAdvanceOrderRevision(models.Model):
    _name = "pos.advance.order.revision"

    order_id = fields.Many2one("pos.advance.order", required=True)
    user_id = fields.Many2one("res.users", required=True)
    snapshot_json_text = fields.Text()
