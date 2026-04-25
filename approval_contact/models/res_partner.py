from odoo import fields, models, _

class ResPartner(models.Model):
    _inherit = "res.partner"

    x_approval_request_id = fields.Many2one(
        "approval.request",
        string="Source Approval Request",
        readonly=True,
        copy=False
    )

    def action_open_source_approval(self):
        self.ensure_one()
        if not self.x_approval_request_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "name": _("Approval Request"),
            "res_model": "approval.request",
            "view_mode": "form",
            "res_id": self.x_approval_request_id.id,
            "target": "current",
        }
