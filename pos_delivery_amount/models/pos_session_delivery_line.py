from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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
    reason = fields.Char(
        string="Reason",
        help="Mandatory for in-session cash delivery. Not required at session closing.",
    )
    is_closing_delivery = fields.Boolean(
        string="At Session Closing",
        readonly=True,
        default=False,
        help="Set when delivery is recorded after the closing cash count. "
        "Does not affect POS cash register balance.",
    )

    @api.constrains("reason", "is_closing_delivery", "amount")
    def _check_reason_for_session_delivery(self):
        for line in self:
            if line.is_closing_delivery:
                continue
            if line.currency_id.compare_amounts(line.amount or 0.0, 0.0) == 0:
                continue
            if not (line.reason or "").strip():
                raise ValidationError(
                    _("A reason is required for in-session cash delivery.")
                )
