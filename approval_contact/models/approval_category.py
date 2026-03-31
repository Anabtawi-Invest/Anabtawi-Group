from odoo import fields, models

class ApprovalCategory(models.Model):
    _inherit = "approval.category"

    x_create_contact_on_approve = fields.Boolean(
        string="Create Contact on Approval",
        help="When enabled, approving a request (request_status='approved') in this category creates a new Contact."
    )
