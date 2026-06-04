from odoo import _, fields, models


class ConfirmSetDefaultCustomerWizard(models.TransientModel):
    _name = "pos.set.default.customer.wizard"
    _description = "Confirm Set Default Customer on POS Orders"

    partner_id = fields.Many2one("res.partner", string="Customer", required=True, readonly=True)
    records_count = fields.Integer(string="Orders to Update", readonly=True)

    def action_confirm(self):
        self.ensure_one()
        updated_count = self.env["pos.order"]._assign_default_customer_to_empty_orders(
            partner_id=self.partner_id.id
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Done"),
                "message": _("Updated %s POS orders with customer %s.")
                % (updated_count, self.partner_id.display_name),
                "type": "success",
                "sticky": False,
            },
        }
