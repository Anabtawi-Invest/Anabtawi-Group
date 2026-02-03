from odoo import models, fields

class POApprovalLine(models.Model):
    _name = "po.approval.line"
    _description = "PO Approval Line"
    _order = "id"

    order_id = fields.Many2one("purchase.order", required=True, ondelete="cascade")
    user_id = fields.Many2one("res.users", required=True)
    group_name = fields.Char()
    state = fields.Selection([
        ("pending", "Pending"),
        ("approved", "Approved"),
    ], default="pending")

