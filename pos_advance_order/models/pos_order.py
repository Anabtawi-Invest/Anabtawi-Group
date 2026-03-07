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

    @api.model_create_multi
    def create(self, vals_list):
        _logger.info("DEBUG REFUND: create called with vals_list = %s", vals_list)

        orders = super().create(vals_list)

        for order in orders:
            _logger.info(
                "DEBUG REFUND: created order id=%s name=%s is_refund=%s",
                order.id, order.name, order.is_refund
            )

            if order.is_refund:
                original_orders = order.lines.mapped("refunded_orderline_id.order_id")

                _logger.info(
                    "DEBUG REFUND: original orders detected %s",
                    original_orders.ids
                )

                for original in original_orders:
                    advance = original.advance_order_id

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
                            original.name
                        )

        return orders
