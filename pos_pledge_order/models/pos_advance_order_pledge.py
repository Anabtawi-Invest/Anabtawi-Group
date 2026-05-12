# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PosAdvanceOrderPledgeRahn(models.Model):
    _inherit = "pos.advance.order.pledge"

    receive_date = fields.Datetime(
        string="Received On",
        readonly=True,
        copy=False,
        help="Date and time when the pledge was collected at POS.",
    )
    state = fields.Selection(
        [
            ("active", "Active"),
            ("returned", "Returned"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="active",
        index=True,
    )
    return_date = fields.Datetime(
        string="Returned On",
        readonly=True,
        copy=False,
        help="Date and time when the pledge was returned and the deposit was reversed.",
    )

    def init(self):
        super().init()
        self.env.cr.execute(
            """
            UPDATE pos_advance_order_pledge
               SET receive_date = create_date
             WHERE receive_date IS NULL
            """
        )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "receive_date" not in vals:
                vals["receive_date"] = fields.Datetime.now()
        return super().create(vals_list)

    @api.model
    def create_from_pos(self, vals):
        """Same as pos_advance_order, plus receive_date on create/update from POS."""
        pos_order_id = vals.get("pos_order_id")
        partner_id = vals.get("partner_id")
        if not pos_order_id or not partner_id:
            raise ValidationError(_("Missing required fields for pledge creation (pos_order_id, partner_id)."))

        pos_order = self.env["pos.order"].sudo().browse(pos_order_id)
        if not pos_order.exists():
            raise ValidationError(_("POS Order not found."))

        advance_order_id = pos_order.advance_order_id.id if getattr(pos_order, "advance_order_id", False) else False

        pledge_product_ids = vals.get("pledge_products") or []
        if not isinstance(pledge_product_ids, list):
            pledge_product_ids = []

        if not pledge_product_ids:
            pledge_product_ids = list({
                l.product_id.id
                for l in pos_order.lines.filtered(lambda l: l.product_id and l.product_id.has_pledge)
            })

        qty_by_product = defaultdict(float)
        for line in pos_order.lines.filtered(lambda l: l.product_id and l.product_id.id in pledge_product_ids):
            if line.product_id.has_pledge:
                qty_by_product[line.product_id.id] += line.qty or 0.0

        if not qty_by_product:
            raise ValidationError(_("No pledge products found to create pledge lines."))

        created = self.browse()
        for product_id, qty in qty_by_product.items():
            product = self.env["product.product"].browse(product_id)
            unit_amount = product.pledge_amount or 0.0

            if advance_order_id:
                existing = self.sudo().search(
                    [("order_id", "=", advance_order_id), ("product_id", "=", product_id)],
                    limit=1,
                )
            else:
                existing = self.sudo().search(
                    [("pos_order_id", "=", pos_order.id), ("product_id", "=", product_id)],
                    limit=1,
                )

            if existing:
                write_vals = {
                    "pos_order_id": pos_order.id,
                    "partner_id": partner_id,
                    "pledge_qty": qty,
                    "pledge_amount_unit": unit_amount,
                    "state": "active",
                    "return_date": False,
                    "return_move_id": False,
                }
                if existing.state == "returned" or not existing.receive_date:
                    write_vals["receive_date"] = fields.Datetime.now()
                existing.write(write_vals)
                created |= existing
                continue

            created |= self.sudo().create(
                {
                    "order_id": advance_order_id,
                    "pos_order_id": pos_order.id,
                    "partner_id": partner_id,
                    "product_id": product_id,
                    "pledge_qty": qty,
                    "pledge_amount_unit": unit_amount,
                    "state": "active",
                }
            )
        return created[:1].id
