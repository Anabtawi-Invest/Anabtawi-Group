# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ResUsers(models.Model):
    _inherit = "res.users"

    portal_van_setup = fields.Boolean(
        string="Create Van Warehouse Setup",
        default=False,
        copy=False,
        help="On user creation only: create a full warehouse, transit location, "
        "push route (like branches), portal destination mapping, and grant "
        "Internal Transfer Portal access.",
    )
    van_warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Van Warehouse",
        readonly=True,
        copy=False,
        check_company=False,
    )
    van_transit_location_id = fields.Many2one(
        "stock.location",
        string="Van Transit Location",
        readonly=True,
        copy=False,
        check_company=False,
    )
    van_customer_id = fields.Many2one(
        "res.partner",
        string="Van Customer",
        copy=False,
        check_company=False,
        help="Fixed commercial customer for this van portal user. "
        "Portal sales use this customer; delivery addresses are children under it.",
    )
    van_pricelist_id = fields.Many2one(
        "product.pricelist",
        string="Van Pricelist",
        copy=False,
        check_company=False,
        help="Pricelist for this van. Portal internal transfers only show these products. "
        "Portal sales use it as the order pricelist and for prices.",
    )

    def _get_van_pricelist_product_ids(self):
        """Product variants covered by the van pricelist item lines."""
        self.ensure_one()
        pricelist = self.van_pricelist_id
        if not pricelist:
            return False
        product_ids = set()
        Product = self.env["product.product"].sudo()
        for item in pricelist.item_ids:
            if item.product_id:
                product_ids.add(item.product_id.id)
            elif item.product_tmpl_id:
                product_ids.update(item.product_tmpl_id.product_variant_ids.ids)
            elif item.categ_id:
                product_ids.update(
                    Product.search([("categ_id", "child_of", item.categ_id.id)]).ids
                )
        return list(product_ids)

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        for user, vals in zip(users, vals_list):
            if vals.get("portal_van_setup"):
                user.sudo()._create_van_stock_configuration()
        return users

    def write(self, vals):
        res = super().write(vals)
        if (
            vals.get("portal_van_setup")
            and not self.env.context.get("skip_van_setup_write_guard")
        ):
            pending = self.filtered(lambda u: u.portal_van_setup and not u.van_warehouse_id)
            if pending:
                raise UserError(
                    _(
                        "Van warehouse setup runs only when creating a new user. "
                        "Create a new portal user with «Create Van Warehouse Setup» enabled."
                    )
                )
        return res

    def action_create_van_stock_configuration(self):
        """Button: run van setup on an existing portal user (once)."""
        self.ensure_one()
        self.sudo()._create_van_stock_configuration()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Van setup created"),
                "message": _(
                    "Warehouse %(wh)s and transit %(transit)s are ready."
                )
                % {
                    "wh": self.van_warehouse_id.display_name,
                    "transit": self.van_transit_location_id.display_name,
                },
                "type": "success",
                "sticky": False,
            },
        }

    def _create_van_stock_configuration(self):
        """Create warehouse + transit + push route + portal map."""
        self.ensure_one()
        if self.van_warehouse_id:
            return self.van_warehouse_id

        if not self.share:
            raise UserError(
                _("Van warehouse setup is only available for portal users.")
            )

        company = self.company_id
        if not company:
            raise UserError(_("Please set a company on the user before van setup."))

        partner_name = (self.partner_id.name or self.login or "").strip()
        if not partner_name:
            raise UserError(_("User must have a partner name for the van warehouse."))

        Warehouse = self.env["stock.warehouse"].sudo().with_company(company)
        supplier = self._van_get_supplier_warehouse(company)
        if not supplier:
            raise UserError(
                _(
                    "No existing warehouse found in company %s. "
                    "Create the main warehouse first, then create the van user."
                )
                % company.display_name
            )
        code = self._van_make_warehouse_code(company)
        name = self._van_make_warehouse_name(company, partner_name)

        warehouse = Warehouse.create(
            {
                "name": name,
                "code": code,
                "company_id": company.id,
                "partner_id": self.partner_id.id,
                "reception_steps": "one_step",
                "delivery_steps": "ship_only",
                "resupply_wh_ids": [(4, supplier.id)],
            }
        )

        transit_name = _("%s-المصنع", warehouse.name)
        barcode = f"{supplier.code}{warehouse.code}"[:32]
        transit = (
            self.env["stock.location"]
            .sudo()
            .with_company(company)
            .create(
                {
                    "name": transit_name,
                    "usage": "internal",
                    "company_id": company.id,
                    "barcode": barcode,
                }
            )
        )

        if not warehouse.int_type_id:
            raise UserError(
                _("Warehouse %s has no Internal Transfers operation type.")
                % warehouse.display_name
            )

        route = (
            self.env["stock.route"]
            .sudo()
            .with_company(company)
            .create(
                {
                    "name": transit_name,
                    "company_id": company.id,
                    "product_selectable": False,
                    "product_categ_selectable": False,
                    "warehouse_selectable": True,
                    "warehouse_ids": [(6, 0, [supplier.id, warehouse.id])],
                }
            )
        )
        self.env["stock.rule"].sudo().with_company(company).create(
            {
                "name": transit_name,
                "route_id": route.id,
                "action": "push",
                "auto": "manual",
                "procure_method": "make_to_stock",
                "location_src_id": transit.id,
                "location_dest_id": warehouse.lot_stock_id.id,
                "picking_type_id": warehouse.int_type_id.id,
                "company_id": company.id,
            }
        )

        Map = self.env["portal.transfer.location.map"].sudo()
        existing = Map.search([("user_id", "=", self.id)], limit=1)
        map_vals = {
            "user_id": self.id,
            "location_id": transit.id,
            "stock_location_id": warehouse.lot_stock_id.id,
            "active": True,
        }
        if existing:
            existing.write(map_vals)
        else:
            Map.create(map_vals)

        group = self.env.ref(
            "portal_internal_transfer.group_portal_internal_transfer",
            raise_if_not_found=False,
        )
        if group and group not in self.group_ids:
            self.sudo().write({"group_ids": [(4, group.id)]})

        self.sudo().with_context(skip_van_setup_write_guard=True).write(
            {
                "van_warehouse_id": warehouse.id,
                "van_transit_location_id": transit.id,
                "portal_van_setup": True,
            }
        )
        return warehouse

    def _van_get_supplier_warehouse(self, company):
        """Main/source warehouse for the company (oldest by id, like Factory)."""
        Warehouse = self.env["stock.warehouse"].sudo()
        self.env.cr.execute(
            """
            SELECT sw.supplier_wh_id
              FROM stock_wh_resupply_table sw
              JOIN stock_warehouse w ON w.id = sw.supplied_wh_id
             WHERE w.company_id = %s
          GROUP BY sw.supplier_wh_id
          ORDER BY COUNT(*) DESC, sw.supplier_wh_id ASC
             LIMIT 1
            """,
            (company.id,),
        )
        row = self.env.cr.fetchone()
        if row:
            return Warehouse.browse(row[0])
        return Warehouse.search(
            [("company_id", "=", company.id)],
            order="id asc",
            limit=1,
        )

    def _van_make_warehouse_code(self, company):
        raw = re.sub(r"[^A-Za-z0-9]", "", self.login or "")[:5].upper()
        if not raw:
            raw = "VAN"
        Warehouse = self.env["stock.warehouse"].sudo().with_context(active_test=False)
        code = raw
        idx = 1
        while Warehouse.search_count(
            [("code", "=", code), ("company_id", "=", company.id)]
        ):
            suffix = str(idx)
            code = (raw[: max(1, 5 - len(suffix))] + suffix)[:5]
            idx += 1
            if idx > 999:
                raise ValidationError(
                    _("Could not generate a unique warehouse code for login %s.")
                    % self.login
                )
        return code

    def _van_make_warehouse_name(self, company, partner_name):
        Warehouse = self.env["stock.warehouse"].sudo().with_context(active_test=False)
        name = partner_name
        idx = 1
        while Warehouse.search_count(
            [("name", "=", name), ("company_id", "=", company.id)]
        ):
            name = f"{partner_name} ({idx})"
            idx += 1
        return name
