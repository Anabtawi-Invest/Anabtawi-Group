# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

class BranchSupplyOrder(models.Model):
    _name = "branch.supply.order"
    _description = "Branch Supply Order via Fleet Transit"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", readonly=True, copy=False, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    state = fields.Selection([
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("approved", "Approved"),
        ("factory_planned", "Factory Planned"),
        ("ready_to_ship", "Ready to Ship"),
        ("loaded", "Loaded (WH → Fleet)"),
        ("in_transit", "In Transit (Driver Verified)"),
        ("received", "Received"),
        ("cancel", "Cancelled"),
    ], default="draft", tracking=True)

    warehouse_id = fields.Many2one(
        "stock.warehouse", string="Source Warehouse (Factory)",
        required=True, tracking=True,
        domain="[('company_id','=',company_id)]",
    )
    branch_warehouse_id = fields.Many2one(
        "stock.warehouse", string="Destination Warehouse (Branch)",
        required=True, tracking=True,
        domain="[('company_id','=',company_id)]",
    )

    fleet_location_id = fields.Many2one(
        "stock.location",
        string="Fleet Transit Location",
        required=True,
        tracking=True,
        domain="[('usage','=','internal'), ('company_id','in',[company_id, False])]",
        help="Transit buffer location. Drivers have no system access; stock moves through this location."
    )

    scheduled_date = fields.Datetime(default=fields.Datetime.now, tracking=True)
    note = fields.Text()

    line_ids = fields.One2many("branch.supply.line", "order_id", string="Products", copy=True)

    picking_wh_to_fleet_id = fields.Many2one("stock.picking", string="WH → Fleet Picking", readonly=True, copy=False)
    picking_fleet_to_branch_id = fields.Many2one("stock.picking", string="Fleet → Branch Picking", readonly=True, copy=False)

    def _get_internal_picking_type(self, warehouse):
        picking_type = warehouse.int_type_id
        if not picking_type:
            raise UserError(_("No Internal Transfer operation type found for warehouse %s.") % (warehouse.display_name,))
        return picking_type

    def _create_internal_picking(self, picking_type, location_src, location_dest, moves):
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": location_src.id,
            "location_dest_id": location_dest.id,
            "company_id": self.company_id.id,
            "origin": self.name,
        })
        move_vals = []
        for product, qty, uom in moves:
            if qty <= 0:
                continue
            move_vals.append({
                "name": product.display_name,
                "product_id": product.id,
                "product_uom": uom.id,
                "product_uom_qty": qty,
                "location_id": location_src.id,
                "location_dest_id": location_dest.id,
                "picking_id": picking.id,
                "company_id": self.company_id.id,
            })
        if not move_vals:
            picking.unlink()
            return False

        self.env["stock.move"].create(move_vals)
        picking.action_confirm()
        picking.action_assign()
        for ml in picking.move_line_ids:
            ml.qty_done = ml.product_uom_qty
        picking.button_validate()
        return picking

    @api.model
    def create(self, vals):
        if vals.get("name", "New") == "New":
            vals["name"] = self.env["ir.sequence"].next_by_code("branch.supply.order") or "New"
        if not vals.get("fleet_location_id"):
            param = self.env["ir.config_parameter"].sudo().get_param("branch_fleet_supply.fleet_location_id")
            if param:
                try:
                    vals["fleet_location_id"] = int(param)
                except Exception:
                    pass
        return super().create(vals)

    # --- Branch ---
    def action_submit(self):
        for order in self:
            if not order.line_ids:
                raise UserError(_("Add at least one product line."))
            order.state = "submitted"

    # --- Manager approval ---
    def action_approve(self):
        for order in self:
            if order.state != "submitted":
                continue
            order.state = "approved"
            order._plan_factory_and_procurement()

    def _plan_factory_and_procurement(self):
        self.ensure_one()
        src_loc = self.warehouse_id.lot_stock_id
        StockQuant = self.env["stock.quant"]
        procurement_lines = []

        for line in self.line_ids:
            if line.requested_qty <= 0:
                continue
            available = StockQuant._get_available_quantity(line.product_id, src_loc, allow_negative=False)
            shortage = max(line.requested_qty - available, 0.0)

            line.sudo().write({
                "available_qty": available,
                "shortage_qty": shortage,
            })

            if shortage > 0:
                bom = self.env["mrp.bom"]._bom_find(line.product_id, company_id=self.company_id.id)
                if bom:
                    mo = self.env["mrp.production"].create({
                        "product_id": line.product_id.id,
                        "product_qty": shortage,
                        "product_uom_id": line.product_uom_id.id,
                        "bom_id": bom.id,
                        "origin": self.name,
                        "company_id": self.company_id.id,
                    })
                    line.sudo().write({"mo_id": mo.id})

                seller = line.product_id.seller_ids[:1]
                if seller and seller.partner_id:
                    procurement_lines.append((seller.partner_id, line.product_id, shortage, line.product_uom_id))
                else:
                    self.activity_schedule(
                        "mail.mail_activity_data_todo",
                        summary=_("Procurement needed: vendor missing"),
                        note=_("Product %s has shortage %.2f and no vendor on product. Please set vendor and purchase.") % (line.product_id.display_name, shortage),
                    )

        if procurement_lines:
            by_vendor = {}
            for vendor, product, qty, uom in procurement_lines:
                if qty <= 0:
                    continue
                by_vendor.setdefault(vendor, []).append((product, qty, uom))

            for vendor, lines in by_vendor.items():
                po = self.env["purchase.order"].create({
                    "partner_id": vendor.id,
                    "company_id": self.company_id.id,
                    "origin": self.name,
                })
                for product, qty, uom in lines:
                    self.env["purchase.order.line"].create({
                        "order_id": po.id,
                        "product_id": product.id,
                        "name": product.display_name,
                        "product_qty": qty,
                        "product_uom": uom.id,
                        "price_unit": 0.0,
                        "date_planned": fields.Datetime.now(),
                    })
                for l in self.line_ids:
                    if l.product_id.seller_ids[:1].partner_id == vendor:
                        l.sudo().write({"po_id": po.id})

        self.state = "factory_planned"

    # --- Factory acceptance ---
    def action_factory_accept(self):
        for order in self:
            if order.state != "factory_planned":
                continue
            order.state = "ready_to_ship"

    # --- Warehouse load ---
    def action_load(self):
        for order in self:
            if order.state != "ready_to_ship":
                continue
            moves = []
            for line in order.line_ids:
                if (line.loaded_qty or 0.0) < 0:
                    raise UserError(_("Loaded quantity cannot be negative."))
                if (line.loaded_qty or 0.0) > 0.0:
                    moves.append((line.product_id, line.loaded_qty, line.product_uom_id))

            picking_type = order._get_internal_picking_type(order.warehouse_id)
            src = order.warehouse_id.lot_stock_id
            dest = order.fleet_location_id
            picking = order._create_internal_picking(picking_type, src, dest, moves)
            order.picking_wh_to_fleet_id = picking.id if picking else False
            order.state = "loaded"

    # --- Warehouse confirm dispatch ---
    def action_confirm_dispatch(self):
        for order in self:
            if order.state != "loaded":
                continue
            order.state = "in_transit"

    # --- Branch receive ---
    def action_receive(self):
        for order in self:
            if order.state != "in_transit":
                continue

            moves = []
            for line in order.line_ids:
                if (line.received_qty or 0.0) < 0:
                    raise UserError(_("Received quantity cannot be negative."))
                if (line.received_qty or 0.0) > 0.0:
                    moves.append((line.product_id, line.received_qty, line.product_uom_id))

            picking_type = order._get_internal_picking_type(order.branch_warehouse_id)
            src = order.fleet_location_id
            dest = order.branch_warehouse_id.lot_stock_id
            picking = order._create_internal_picking(picking_type, src, dest, moves)
            order.picking_fleet_to_branch_id = picking.id if picking else False

            for line in order.line_ids:
                gap = max((line.loaded_qty or 0.0) - (line.received_qty or 0.0), 0.0)
                if gap > 0:
                    case = self.env["fleet.discrepancy.case"].create({
                        "company_id": order.company_id.id,
                        "order_id": order.id,
                        "line_id": line.id,
                        "product_id": line.product_id.id,
                        "uom_id": line.product_uom_id.id,
                        "missing_qty": gap,
                    })
                    if case.name == "New":
                        case.name = self.env["ir.sequence"].next_by_code("fleet.discrepancy.case") or _("New")

            order.state = "received"

    def action_cancel(self):
        for order in self:
            if order.state in ("received", "in_transit", "loaded"):
                raise UserError(_("You cannot cancel after loading/dispatch/receiving. Create a revision instead."))
            order.state = "cancel"
