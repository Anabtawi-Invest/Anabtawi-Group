from odoo import fields, models


class PosSessionDeliveryLine(models.Model):
    _name = "pos.session.delivery.line"
    _description = "POS Session Delivery Amount Line"
    _order = "id asc"

    session_id = fields.Many2one(
        "pos.session",
        string="Session",
        required=True,
        ondelete="cascade",
        index=True,
    )
    amount = fields.Monetary(required=True)
    currency_id = fields.Many2one(
        related="session_id.currency_id",
        store=True,
        readonly=True,
    )
    move_id = fields.Many2one(
        "account.move",
        string="Journal Entry",
        readonly=True,
        copy=False,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Processed By",
        readonly=True,
        default=lambda self: self.env.user,
    )
    is_closing_delivery = fields.Boolean(
        string="At Session Closing",
        readonly=True,
        default=False,
        help="Set when delivery is recorded after the closing cash count. "
        "Does not affect POS cash register balance.",
    )
