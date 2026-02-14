# -*- coding: utf-8 -*-

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class StockScrap(models.Model):
    _inherit = "stock.scrap"

    @api.model
    def pos_create_scrap(self, payload):
        """Create (and validate) a stock.scrap from the POS UI.

        Expected payload keys:
        - product_id (required)
        - scrap_qty (required)
        - location_id (required)
        - scrap_location_id (required)
        - lot_id (optional)
        - package_id (optional)
        - owner_id (optional)
        - origin (optional)
        - scrap_reason_tag_ids (optional) list[int]
        - validate (optional, default True)
        """
        payload = payload or {}

        def _to_int(v):
            try:
                return int(v) if v else 0
            except Exception:
                return 0

        product_id = _to_int(payload.get("product_id"))
        location_id = _to_int(payload.get("location_id"))
        scrap_location_id = _to_int(payload.get("scrap_location_id"))
        lot_id = _to_int(payload.get("lot_id"))
        package_id = _to_int(payload.get("package_id"))
        owner_id = _to_int(payload.get("owner_id"))
        origin = payload.get("origin") or ""
        scrap_reason_tag_ids = payload.get("scrap_reason_tag_ids") or []
        validate = payload.get("validate", True)

        try:
            scrap_qty = float(payload.get("scrap_qty") or 0.0)
        except Exception:
            scrap_qty = 0.0

        if not product_id:
            raise UserError(_("Product is required."))
        if not location_id:
            raise UserError(_("Source location is required."))
        if not scrap_location_id:
            raise UserError(_("Scrap location is required."))
        if scrap_qty <= 0:
            raise UserError(_("You can only enter positive quantities."))

        product = self.env["product.product"].browse(product_id).exists()
        if not product:
            raise UserError(_("Invalid product."))

        vals = {
            "product_id": product_id,
            "scrap_qty": scrap_qty,
            "location_id": location_id,
            "scrap_location_id": scrap_location_id,
            "origin": origin,
        }
        if lot_id:
            vals["lot_id"] = lot_id
        if package_id:
            vals["package_id"] = package_id
        if owner_id:
            vals["owner_id"] = owner_id
        if scrap_reason_tag_ids:
            try:
                reason_ids = [int(x) for x in scrap_reason_tag_ids if x]
            except Exception:
                reason_ids = []
            if reason_ids:
                vals["scrap_reason_tag_ids"] = [(6, 0, reason_ids)]

        scrap = self.create(vals)

        if validate:
            if product.is_storable:
                precision = self.env["decimal.precision"].precision_get("Product Unit")
                available_qty = product.with_context(
                    location=location_id,
                    lot_id=lot_id or False,
                    package_id=package_id or False,
                    owner_id=owner_id or False,
                    strict=True,
                ).qty_available

                # qty_available is in product's base uom
                requested_qty_in_product_uom = scrap.product_uom_id._compute_quantity(
                    scrap.scrap_qty, product.uom_id
                )

                if float_compare(available_qty, requested_qty_in_product_uom, precision_digits=precision) < 0:
                    raise UserError(
                        _(
                            "Insufficient quantity to scrap.\n\nAvailable: %(avail)s\nRequested: %(req)s",
                            avail=available_qty,
                            req=requested_qty_in_product_uom,
                        )
                    )

            scrap.do_scrap()

        return {"id": scrap.id, "name": scrap.name, "state": scrap.state}

