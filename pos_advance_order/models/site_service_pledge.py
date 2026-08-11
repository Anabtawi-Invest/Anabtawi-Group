# -*- coding: utf-8 -*-
"""Site Service menu product → pledge product mapping for advance orders."""

from odoo import api, fields, models


class PosAdvanceOrderLinePledge(models.Model):
    _inherit = "pos.advance.order.line"

    is_site_service_pledge_line = fields.Boolean(
        string="Site Service Pledge Line",
        default=False,
        help="Auto-added pledge product line mapped from a Site Service menu product.",
    )
    source_menu_product_id = fields.Many2one(
        "product.product",
        string="Source Menu Product",
        help="Site Service menu product that triggered this pledge line.",
    )


class PosAdvanceOrderSiteServicePledge(models.Model):
    _inherit = "pos.advance.order"

    @api.model
    def _get_site_service_pledge_map(self):
        """menu product id → pledge product record."""
        if "pos.site.service.product.line" not in self.env:
            return {}
        lines = self.env["pos.site.service.product.line"].sudo().search([
            ("menu_id.active", "=", True),
            ("menu_id.enable_site_service", "=", True),
            ("pledge_product_id", "!=", False),
        ])
        return {line.product_id.id: line.pledge_product_id for line in lines if line.product_id}

    @api.model
    def _expand_line_vals_with_site_service_pledges(self, line_vals_list, site_service_enabled):
        """Append pledge product lines for mapped Site Service menu products."""
        if site_service_enabled or not line_vals_list:
            return list(line_vals_list)
        mapping = self._get_site_service_pledge_map()
        if not mapping:
            return list(line_vals_list)
        expanded = list(line_vals_list)
        for cmd in line_vals_list:
            if not isinstance(cmd, (list, tuple)) or len(cmd) < 3 or cmd[0] != 0:
                continue
            vals = dict(cmd[2])
            if vals.get("is_site_service_pledge_line"):
                continue
            menu_product_id = vals.get("product_id")
            pledge_product = mapping.get(menu_product_id)
            if not pledge_product:
                continue
            qty = vals.get("product_qty") or 0.0
            if qty <= 0:
                continue
            expanded.append(
                (
                    0,
                    0,
                    {
                        "product_id": pledge_product.id,
                        "product_qty": qty,
                        "price_unit": vals.get("price_unit")
                        if vals.get("product_id") == pledge_product.id
                        else pledge_product.lst_price,
                        "discount": 0.0,
                        "tax_ids": [(6, 0, pledge_product.taxes_id.ids)],
                        "is_site_service_pledge_line": True,
                        "source_menu_product_id": menu_product_id,
                    },
                )
            )
            # Use list price for pledge lines unless explicitly the same product
            expanded[-1][2]["price_unit"] = pledge_product.lst_price
        return expanded

    def _sync_site_service_pledge_records(self):
        """Create/update pending pos.advance.order.pledge rows from menu lines."""
        Pledge = self.env["pos.advance.order.pledge"].sudo()
        for order in self:
            if not order._pledge_applies():
                order.pledge_line_ids.filtered(lambda p: p.state == "pending").write(
                    {"state": "cancelled"}
                )
                continue
            mapping = order._get_site_service_pledge_map()
            menu_lines = order.line_ids.filtered(
                lambda l: l.product_id and not l.is_site_service_pledge_line and not l.display_type
            )
            touched_ids = self.env["pos.advance.order.pledge"]
            for menu_line in menu_lines:
                pledge_product = mapping.get(menu_line.product_id.id)
                if not pledge_product:
                    continue
                unit = pledge_product.lst_price
                existing = Pledge.search(
                    [
                        ("order_id", "=", order.id),
                        ("advance_line_id", "=", menu_line.id),
                    ],
                    limit=1,
                )
                vals = {
                    "partner_id": order.partner_id.id,
                    "product_id": pledge_product.id,
                    "source_product_id": menu_line.product_id.id,
                    "advance_line_id": menu_line.id,
                    "pledge_qty": menu_line.product_qty,
                    "pledge_amount_unit": unit,
                    "state": "pending",
                }
                if existing:
                    existing.write(vals)
                    touched_ids |= existing
                else:
                    touched_ids |= Pledge.create(dict(vals, order_id=order.id))
            stale = order.pledge_line_ids.filtered(
                lambda p: p.state == "pending" and p.id not in touched_ids.ids
            )
            if stale:
                stale.write({"state": "cancelled"})

    def _activate_site_service_pledges_on_completion(self, pos_order, session):
        """Mark pending pledge rows active once the completion POS order is paid."""
        self.ensure_one()
        if not self._pledge_applies():
            return
        pending = self.pledge_line_ids.filtered(lambda p: p.state == "pending")
        if not pending:
            return
        pending.write(
            {
                "state": "active",
                "pos_order_id": pos_order.id,
                "receive_date": fields.Datetime.now(),
                "receive_pos_session_id": session.id,
            }
        )
