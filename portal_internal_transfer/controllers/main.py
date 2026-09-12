# -*- coding: utf-8 -*-
import logging

from odoo import _, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from odoo.addons.portal.controllers.portal import pager as portal_pager

_logger = logging.getLogger(__name__)

GROUP_XMLID = "portal_internal_transfer.group_portal_internal_transfer"


class PortalInternalTransfer(http.Controller):

    def _ensure_access(self):
        if request.env.user._is_public() or not request.env.user.has_group(GROUP_XMLID):
            raise AccessError(_("You do not have access to Internal Transfer Portal."))

    def _get_my_picking(self, picking_id):
        picking = request.env["stock.picking"].sudo().browse(int(picking_id)).exists()
        if (
            not picking
            or picking.create_uid.id != request.env.user.id
            or picking.picking_type_id.code != "internal"
        ):
            raise AccessError(_("Transfer not found or access denied."))
        return picking

    def _get_internal_picking_type(self):
        PickingType = request.env["stock.picking.type"].sudo()
        company = request.env.company
        picking_type = PickingType.search(
            [
                ("code", "=", "internal"),
                ("company_id", "in", [False, company.id]),
            ],
            limit=1,
            order="company_id desc, sequence, id",
        )
        if not picking_type:
            raise UserError(_("No internal transfer operation type is configured."))
        return picking_type

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------

    @http.route("/my/transfers/create", type="http", auth="user", website=True)
    def portal_transfer_create(self, **kwargs):
        self._ensure_access()
        return request.render(
            "portal_internal_transfer.portal_transfer_create",
            {"page_name": "portal_transfer_create"},
        )

    @http.route(
        ["/my/transfers", "/my/transfers/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_transfer_list(self, page=1, **kwargs):
        self._ensure_access()
        Picking = request.env["stock.picking"].sudo()
        domain = [
            ("create_uid", "=", request.env.user.id),
            ("picking_type_id.code", "=", "internal"),
        ]
        total = Picking.search_count(domain)
        pager = portal_pager(url="/my/transfers", total=total, page=page, step=20, url_args={})
        pickings = Picking.search(
            domain,
            order="create_date desc, id desc",
            limit=20,
            offset=pager["offset"],
        )
        return request.render(
            "portal_internal_transfer.portal_transfer_list",
            {
                "page_name": "portal_transfer_list",
                "pickings": pickings,
                "pager": pager,
            },
        )

    @http.route("/my/transfers/<int:picking_id>", type="http", auth="user", website=True)
    def portal_transfer_detail(self, picking_id, **kwargs):
        self._ensure_access()
        picking = self._get_my_picking(picking_id)
        return request.render(
            "portal_internal_transfer.portal_transfer_detail",
            {
                "page_name": "portal_transfer_detail",
                "picking": picking,
            },
        )

    # ------------------------------------------------------------------
    # JSON / HTTP API
    # ------------------------------------------------------------------

    @http.route("/my/transfers/api/locations", type="jsonrpc", auth="user", website=True)
    def api_locations(self, term="", **kwargs):
        self._ensure_access()
        return self._search_locations(term)

    @http.route(
        "/my/transfers/api/locations/http",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
        csrf=False,
    )
    def api_locations_http(self, term="", **kwargs):
        self._ensure_access()
        return request.make_json_response(self._search_locations(term))

    def _search_locations(self, term):
        term = (term or "").strip()
        Location = request.env["stock.location"].sudo()
        domain = [
            ("usage", "=", "internal"),
            ("active", "=", True),
            ("company_id", "in", [False, request.env.company.id]),
        ]
        if term:
            domain += [
                "|",
                "|",
                ("name", "ilike", term),
                ("complete_name", "ilike", term),
                ("barcode", "ilike", term),
            ]
        locations = Location.search(domain, limit=30, order="complete_name, id")
        return [
            {
                "id": loc.id,
                "name": loc.complete_name or loc.name,
            }
            for loc in locations
        ]

    @http.route("/my/transfers/api/products", type="jsonrpc", auth="user", website=True)
    def api_products(self, term="", offset=0, limit=60, **kwargs):
        self._ensure_access()
        term = (term or "").strip()
        try:
            offset = max(int(offset or 0), 0)
        except (TypeError, ValueError):
            offset = 0
        try:
            limit = min(max(int(limit or 60), 1), 200)
        except (TypeError, ValueError):
            limit = 60

        domain = [
            ("active", "=", True),
            ("is_storable", "=", True),
        ]
        if term:
            domain += [
                "|",
                "|",
                ("name", "ilike", term),
                ("default_code", "ilike", term),
                ("barcode", "ilike", term),
            ]

        Product = request.env["product.product"].sudo()
        total = Product.search_count(domain)
        products = Product.search(domain, limit=limit, offset=offset, order="default_code, name, id")
        return {
            "products": [
                {
                    "id": p.id,
                    "name": p.display_name,
                    "image_url": f"/web/image/product.product/{p.id}/image_128",
                    "uom": p.uom_id.name,
                }
                for p in products
            ],
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(products) < total,
        }

    @http.route("/my/transfers/api/confirm", type="jsonrpc", auth="user", website=True)
    def api_confirm(self, location_id=None, location_dest_id=None, lines=None, **kwargs):
        self._ensure_access()
        if not location_id or not location_dest_id:
            raise ValidationError(_("Please select source and destination locations."))
        if int(location_id) == int(location_dest_id):
            raise ValidationError(_("Source and destination must be different."))

        Location = request.env["stock.location"].sudo()
        source = Location.browse(int(location_id)).exists()
        dest = Location.browse(int(location_dest_id)).exists()
        if not source or source.usage != "internal" or not source.active:
            raise ValidationError(_("Invalid source location."))
        if not dest or dest.usage != "internal" or not dest.active:
            raise ValidationError(_("Invalid destination location."))

        lines = lines or []
        move_commands = []
        for line in lines:
            product_id = int(line.get("product_id") or 0)
            qty = float(line.get("qty") or 0)
            if not product_id or qty <= 0:
                continue
            product = request.env["product.product"].sudo().browse(product_id).exists()
            if not product or not product.is_storable:
                raise ValidationError(_("Invalid product selected."))
            move_commands.append(
                (
                    0,
                    0,
                    {
                        "product_id": product.id,
                        "product_uom_qty": qty,
                        "uom_id": product.uom_id.id,
                        "location_id": source.id,
                        "location_dest_id": dest.id,
                    },
                )
            )
        if not move_commands:
            raise ValidationError(_("Please add at least one product with quantity."))

        picking_type = self._get_internal_picking_type()
        picking = (
            request.env["stock.picking"]
            .sudo()
            .create(
                {
                    "picking_type_id": picking_type.id,
                    "location_id": source.id,
                    "location_dest_id": dest.id,
                    "origin": _("Portal Internal Transfer"),
                    "move_ids": move_commands,
                }
            )
        )
        picking.action_confirm()
        return {
            "picking_id": picking.id,
            "picking_name": picking.name,
            "redirect_url": f"/my/transfers/{picking.id}",
        }

    @http.route("/my/transfers/api/cancel", type="jsonrpc", auth="user", website=True)
    def api_cancel(self, picking_id=None, **kwargs):
        self._ensure_access()
        picking = self._get_my_picking(picking_id)
        if picking.state == "cancel":
            return {"ok": True, "message": _("Transfer is already cancelled.")}
        if picking.state == "done":
            raise UserError(_("Done transfers cannot be cancelled."))
        picking.action_cancel()
        return {"ok": True, "message": _("Transfer cancelled successfully.")}
