import logging
from odoo import models, api,fields

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = "pos.order"

    is_advance_generated = fields.Boolean(
        string="Advance Generated",
        default=False,
        help="Technical flag used to exclude this order from POS session closing accounting (advance module flow).",
    )
    advance_order_id = fields.Many2one(
        "pos.advance.order",
        string="Advance Order",
        readonly=True,
        copy=False,
        index=True,
    )

    advance_pledge_line_ids = fields.One2many(
        "pos.advance.order.pledge",
        "pos_order_id",
        string="Pledge Lines",
        readonly=True,
        copy=False,
    )

class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)

        for line in lines:
            if line.refunded_orderline_id:
                original_order = line.refunded_orderline_id.order_id

                _logger.info(
                    "DEBUG REFUND: refund line detected. original order %s",
                    original_order.name
                )

                advance = original_order.advance_order_id

                if advance:
                    _logger.info(
                        "DEBUG REFUND: advance found %s state=%s",
                        advance.name, advance.state
                    )

                    if advance.state != "cancel":
                        advance.write({"state": "cancel"})
                        _logger.info(
                            "DEBUG REFUND: advance %s cancelled",
                            advance.name
                        )
                else:
                    _logger.info(
                        "DEBUG REFUND: no advance linked to order %s",
                        original_order.name
                    )

        return lines
