# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tools import float_compare, float_is_zero, float_round

_logger = logging.getLogger(__name__)


class PosCakeOrder(models.Model):
    _name = "pos.cake.order"
    _description = "Custom Cake Order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="Order Number", required=True, readonly=True, default="New", copy=False)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("waiting_payment", "Waiting for Payment"),
            ("paid", "Paid"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
    )
    partner_id = fields.Many2one("res.partner", string="Customer", required=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )
    pos_session_id = fields.Many2one("pos.session", string="POS Session", readonly=True)
    pos_order_id = fields.Many2one("pos.order", string="POS Order", readonly=True, copy=False)
    user_id = fields.Many2one(
        "res.users",
        string="Cashier",
        default=lambda self: self.env.user,
        readonly=True,
    )
    date_order = fields.Datetime(string="Date", default=fields.Datetime.now, required=True)
    cake_size_id = fields.Many2one("cake.size", string="Cake Size", required=True, readonly=True)
    pieces = fields.Integer(string="Cake Pieces", required=True, readonly=True)
    product_id = fields.Many2one(
        "product.product",
        string="Cake Product",
        related="cake_size_id.product_id",
        store=True,
        readonly=True,
    )
    sugar_paste = fields.Boolean(string="Contains Sugar Paste", readonly=True)
    component_line_ids = fields.One2many(
        "pos.cake.order.component",
        "order_id",
        string="Selected Components",
        readonly=True,
    )
    total_components_cost = fields.Monetary(
        string="Total Components Cost",
        currency_field="currency_id",
        readonly=True,
    )
    cake_base_cost = fields.Monetary(
        string="Cake Base",
        currency_field="currency_id",
        readonly=True,
    )
    price_before_tax = fields.Monetary(
        string="Selling Price Before Tax",
        currency_field="currency_id",
        readonly=True,
    )
    tax_amount = fields.Monetary(string="Tax", currency_field="currency_id", readonly=True)
    final_price = fields.Monetary(
        string="Final Selling Price",
        currency_field="currency_id",
        readonly=True,
    )
    production_id = fields.Many2one(
        "mrp.production",
        string="Manufacturing Order",
        readonly=True,
        copy=False,
    )
    pos_config_id = fields.Many2one("pos.config", string="POS Config", readonly=True)
    note = fields.Text(string="Note", readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("pos.cake.order") or "New"
        return super().create(vals_list)

    @api.model
    def _get_pricing_params(self, company=None):
        company = company or self.env.company
        divisor = company.cake_cost_divisor or 0.63
        tax_rate = company.cake_tax_rate or 16.0
        overhead_percent = company.cake_overhead or 0.0
        if float_is_zero(overhead_percent, precision_digits=6):
            overhead_divisor = 1.0
        else:
            if overhead_percent >= 100.0:
                raise ValidationError(_("Overhead must be less than 100%."))
            overhead_divisor = (100.0 - overhead_percent) / 100.0
            if float_is_zero(overhead_divisor, precision_digits=6):
                raise ValidationError(_("Overhead must be less than 100%."))
        if float_is_zero(divisor, precision_digits=6):
            raise ValidationError(_("Cost divisor must be greater than zero."))
        return overhead_divisor, divisor, tax_rate

    @api.model
    def _compute_prices(self, total_cost, company=None):
        company = company or self.env.company
        currency = company.currency_id
        rounding = currency.rounding or 0.01
        overhead_divisor, divisor, tax_rate = self._get_pricing_params(company)
        cost_after_overhead = float_round(total_cost / overhead_divisor, precision_rounding=rounding)
        price_before_tax = float_round(cost_after_overhead / divisor, precision_rounding=rounding)
        tax_amount = float_round(price_before_tax * (tax_rate / 100.0), precision_rounding=rounding)
        final_price = float_round(price_before_tax + tax_amount, precision_rounding=rounding)
        return total_cost, price_before_tax, tax_amount, final_price

    @api.model
    def _prepare_component_lines(self, selected_lines, pieces=1):
        """selected_lines: list of dicts with category_line_id."""
        CategoryLine = self.env["cake.category.line"]
        component_vals = []
        total_cost = 0.0
        pieces = pieces or 1
        for item in selected_lines:
            line_id = int(item.get("category_line_id") or 0)
            category_line = CategoryLine.browse(line_id).exists()
            if not category_line:
                continue
            line_total = category_line.cost * pieces
            component_vals.append(
                {
                    "category_id": category_line.category_id.id,
                    "category_line_id": category_line.id,
                    "product_id": category_line.product_id.id,
                    "configured_qty": 1.0,
                    "unit_cost": category_line.cost,
                    "total_cost": line_total,
                }
            )
            total_cost += line_total
        return component_vals, total_cost

    @api.model
    def _get_sugar_paste_total_cost(self, company, pieces, sugar_paste=False):
        if not sugar_paste:
            return 0.0, False, 0.0, 0.0
        unit_cost, product = self._add_sugar_paste_cost(company, True)
        qty_per_piece = company.cake_sugar_paste_qty or 1.0
        total_cost = unit_cost * qty_per_piece * (pieces or 1)
        return total_cost, product, qty_per_piece, unit_cost

    @api.model
    def _add_sugar_paste_cost(self, company, sugar_paste):
        if not sugar_paste:
            return 0.0, False
        product = company.cake_sugar_paste_product_id
        if not product:
            raise ValidationError(
                _("Sugar Paste Product is not configured. Please set it in Custom Cake Settings.")
            )
        cost = company.cake_sugar_paste_cost
        if float_is_zero(cost, precision_digits=6):
            cost = product.standard_price
        return cost, product

    @api.model
    def create_from_pos(self, payload):
        """Create cake order and manufacturing order from POS payload."""
        partner_id = payload.get("partner_id")
        cake_size_id = payload.get("cake_size_id")
        selected_lines = payload.get("selected_lines") or []
        sugar_paste = bool(payload.get("sugar_paste"))
        pay_later = bool(payload.get("pay_later"))
        pos_config_id = payload.get("pos_config_id")
        pos_session_id = payload.get("pos_session_id")
        note = (payload.get("note") or "").strip()

        if not partner_id:
            raise ValidationError(_("Customer is required."))
        if not cake_size_id:
            raise ValidationError(_("Cake size is required."))
        if not selected_lines:
            raise ValidationError(_("Please select at least one cake component."))

        partner = self.env["res.partner"].sudo().browse(int(partner_id)).exists()
        if not partner:
            raise ValidationError(_("Invalid customer."))

        cake_size = self.env["cake.size"].sudo().browse(int(cake_size_id)).exists()
        if not cake_size:
            raise ValidationError(_("Invalid cake size."))
        if not cake_size.product_id:
            raise ValidationError(_("The selected cake size has no POS product configured."))
        if cake_size.product_id.type != "consu":
            raise ValidationError(
                _(
                    "The cake size product must be of type Goods (not Service) "
                    "so a manufacturing order can be created."
                )
            )

        pos_config = self.env["pos.config"].sudo().browse(int(pos_config_id)).exists()
        if not pos_config:
            raise ValidationError(_("Invalid POS configuration."))
        if not pos_config.enable_custom_cake:
            raise UserError(_("Custom Cake is not enabled on this Point of Sale."))

        company = pos_config.company_id
        component_vals, total_cost = self._prepare_component_lines(
            selected_lines, cake_size.pieces
        )
        if not component_vals:
            raise ValidationError(_("Please select at least one valid cake component."))

        sugar_total, sugar_product, sugar_qty, sugar_unit_cost = self._get_sugar_paste_total_cost(
            company, cake_size.pieces, sugar_paste
        )
        if sugar_paste:
            total_cost += sugar_total
            component_vals.append(
                {
                    "category_id": False,
                    "category_line_id": False,
                    "product_id": sugar_product.id,
                    "configured_qty": sugar_qty,
                    "unit_cost": sugar_unit_cost,
                    "total_cost": sugar_total,
                    "is_sugar_paste": True,
                }
            )

        cake_base_cost = cake_size.cake_base_cost or 0.0
        total_cost += cake_base_cost

        _, price_before_tax, tax_amount, final_price = self._compute_prices(total_cost, company)

        order_vals = {
            "partner_id": partner.id,
            "company_id": company.id,
            "pos_config_id": pos_config.id,
            "pos_session_id": int(pos_session_id) if pos_session_id else False,
            "cake_size_id": cake_size.id,
            "pieces": cake_size.pieces,
            "sugar_paste": sugar_paste,
            "cake_base_cost": cake_base_cost,
            "total_components_cost": total_cost,
            "price_before_tax": price_before_tax,
            "tax_amount": tax_amount,
            "final_price": final_price,
            "state": "waiting_payment" if pay_later else "waiting_payment",
            "note": note or False,
            "component_line_ids": [Command.create(vals) for vals in component_vals],
        }
        cake_order = self.sudo().create(order_vals)
        cake_order.flush_recordset(["product_id"])
        production = cake_order._create_manufacturing_order()
        cake_order.write({"production_id": production.id})
        return cake_order._prepare_pos_response()

    def _get_manufacturing_picking_type(self):
        self.ensure_one()
        PickingType = self.env["stock.picking.type"].sudo()
        picking_type = PickingType.search(
            [
                ("code", "=", "mrp_operation"),
                ("company_id", "=", self.company_id.id),
            ],
            limit=1,
        )
        if not picking_type:
            warehouse = self.env["stock.warehouse"].sudo().search(
                [("company_id", "=", self.company_id.id)], limit=1
            )
            if warehouse and warehouse.manufacture_pull_id:
                picking_type = warehouse.manufacture_pull_id.picking_type_id
        if not picking_type:
            raise UserError(
                _(
                    "No manufacturing operation type found for company %(company)s. "
                    "Please configure Manufacturing for this company.",
                )
                % {"company": self.company_id.display_name}
            )
        return picking_type

    def _create_manufacturing_order(self):
        self.ensure_one()
        if self.production_id:
            return self.production_id

        if not self.product_id:
            raise UserError(_("The selected cake size has no product configured."))

        picking_type = self._get_manufacturing_picking_type()
        move_raw_vals = []
        for comp in self.component_line_ids:
            qty = comp.configured_qty * self.pieces
            if float_is_zero(qty, precision_rounding=comp.product_id.uom_id.rounding or 0.01):
                continue
            move_raw_vals.append(
                Command.create(
                    {
                        "product_id": comp.product_id.id,
                        "product_uom_qty": qty,
                        "product_uom": comp.product_id.uom_id.id,
                        "company_id": self.company_id.id,
                    }
                )
            )
        if not move_raw_vals:
            raise UserError(_("No manufacturing components found for this cake order."))

        mo_vals = {
            "company_id": self.company_id.id,
            "product_id": self.product_id.id,
            "product_qty": 1.0,
            "product_uom_id": self.product_id.uom_id.id,
            "bom_id": False,
            "origin": self.name,
            "picking_type_id": picking_type.id,
            "location_src_id": picking_type.default_location_src_id.id,
            "location_dest_id": picking_type.default_location_dest_id.id,
            "move_raw_ids": move_raw_vals,
        }
        if not mo_vals["location_src_id"] or not mo_vals["location_dest_id"]:
            raise UserError(
                _(
                    "Manufacturing locations are not configured on operation type %(operation)s.",
                )
                % {"operation": picking_type.display_name}
            )
        production = (
            self.env["mrp.production"]
            .sudo()
            .with_company(self.company_id)
            .create(mo_vals)
        )
        production.action_confirm()
        _logger.info(
            "Manufacturing order %s created for cake order %s",
            production.name,
            self.name,
        )
        return production

    def action_create_manufacturing_order(self):
        for order in self:
            if order.production_id:
                continue
            production = order._create_manufacturing_order()
            order.production_id = production.id
        return True

    def _prepare_pos_response(self):
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state,
            "partner_id": self.partner_id.id,
            "partner_name": self.partner_id.name,
            "product_id": self.product_id.id,
            "product_name": self.product_id.display_name,
            "pieces": self.pieces,
            "sugar_paste": self.sugar_paste,
            "cake_base_cost": self.cake_base_cost,
            "total_components_cost": self.total_components_cost,
            "price_before_tax": self.price_before_tax,
            "tax_amount": self.tax_amount,
            "final_price": self.final_price,
            "production_id": self.production_id.id or False,
            "production_name": self.production_id.name or False,
            "date_order": fields.Datetime.to_string(self.date_order),
            "note": self.note or "",
        }

    def action_mark_paid(self, pos_order=None):
        for order in self:
            if order.state == "cancelled":
                raise UserError(_("Cancelled cake orders cannot be paid."))
            order.write(
                {
                    "state": "paid",
                    "pos_order_id": pos_order.id if pos_order else order.pos_order_id.id,
                }
            )

    def action_cancel(self):
        for order in self:
            if order.state == "paid":
                raise UserError(_("Paid cake orders cannot be cancelled."))
            if order.production_id and order.production_id.state not in ("done", "cancel"):
                order.production_id.action_cancel()
            order.state = "cancelled"

    @api.model
    def search_for_pos(self, query="", limit=50):
        domain = [("state", "=", "waiting_payment")]
        if query:
            domain = [
                "&",
                ("state", "=", "waiting_payment"),
                "|",
                ("name", "ilike", query),
                ("partner_id.name", "ilike", query),
            ]
        orders = self.sudo().search(domain, limit=limit, order="date_order desc")
        return [
            {
                "id": order.id,
                "name": order.name,
                "partner_name": order.partner_id.name,
                "pieces": order.pieces,
                "state": order.state,
                "date_order": fields.Datetime.to_string(order.date_order),
                "final_price": order.final_price,
                "product_name": order.product_id.display_name,
                "note": order.note or "",
            }
            for order in orders
        ]

    @api.model
    def get_pos_config_data(self, pos_config_id=None):
        """Return configuration data for POS popup."""
        company = self.env.company
        if pos_config_id:
            pos_config = self.env["pos.config"].sudo().browse(int(pos_config_id)).exists()
            if pos_config:
                company = pos_config.company_id
        lang = self.env.user.lang or self.env.lang or "en_US"
        Category = self.env["cake.category"].with_context(lang=lang)

        categories = Category.search([("active", "=", True)])
        category_data = []
        for category in categories:
            lines = []
            for line in category.line_ids.filtered(lambda l: l.active and l.product_id):
                lines.append(
                    {
                        "id": line.id,
                        "product_id": line.product_id.id,
                        "product_name": line.product_id.with_context(lang=lang).display_name,
                        "cost": line.cost,
                    }
                )
            category_data.append(
                {
                    "id": category.id,
                    "name": category.name,
                    "lines": lines,
                }
            )

        sizes = self.env["cake.size"].search([("active", "=", True)])
        size_data = [
            {
                "id": size.id,
                "pieces": size.pieces,
                "name": size.name,
                "product_id": size.product_id.id,
                "product_name": size.product_id.with_context(lang=lang).display_name,
                "cake_base_cost": size.cake_base_cost or 0.0,
            }
            for size in sizes
        ]

        sugar_product = company.cake_sugar_paste_product_id
        sugar_cost = company.cake_sugar_paste_cost
        if sugar_product and float_is_zero(sugar_cost, precision_digits=6):
            sugar_cost = sugar_product.standard_price

        return {
            "categories": category_data,
            "sizes": size_data,
            "sugar_paste_product_id": sugar_product.id if sugar_product else False,
            "sugar_paste_cost": sugar_cost or 0.0,
            "sugar_paste_qty": company.cake_sugar_paste_qty or 1.0,
            "cost_divisor": company.cake_cost_divisor or 0.63,
            "overhead": company.cake_overhead or 0.0,
            "tax_rate": company.cake_tax_rate or 16.0,
            "currency_id": company.currency_id.id,
        }

    @api.model
    def compute_preview_prices(self, payload):
        """Compute prices for live preview in POS without creating records."""
        company = self.env.company
        selected_lines = payload.get("selected_lines") or []
        sugar_paste = bool(payload.get("sugar_paste"))
        cake_size_id = payload.get("cake_size_id")
        pieces = 1
        cake_base_cost = 0.0
        if cake_size_id:
            cake_size = self.env["cake.size"].sudo().browse(int(cake_size_id)).exists()
            if cake_size:
                pieces = cake_size.pieces
                cake_base_cost = cake_size.cake_base_cost or 0.0
        _, total_cost = self._prepare_component_lines(selected_lines, pieces)
        sugar_total, _product, _qty, _unit_cost = self._get_sugar_paste_total_cost(
            company, pieces, sugar_paste
        )
        total_cost += sugar_total
        total_cost += cake_base_cost
        _total, price_before_tax, tax_amount, final_price = self._compute_prices(total_cost, company)
        return {
            "total_components_cost": total_cost,
            "cake_base_cost": cake_base_cost,
            "price_before_tax": price_before_tax,
            "tax_amount": tax_amount,
            "final_price": final_price,
        }


class PosCakeOrderComponent(models.Model):
    _name = "pos.cake.order.component"
    _description = "Custom Cake Order Component"

    order_id = fields.Many2one("pos.cake.order", required=True, ondelete="cascade")
    category_id = fields.Many2one("cake.category", string="Category")
    category_line_id = fields.Many2one("cake.category.line", string="Category Line")
    product_id = fields.Many2one("product.product", string="Product", required=True)
    configured_qty = fields.Float(string="Configured Qty", digits="Product Unit")
    unit_cost = fields.Float(string="Unit Cost", digits="Product Price")
    total_cost = fields.Float(string="Total Cost", digits="Product Price")
    is_sugar_paste = fields.Boolean(string="Is Sugar Paste", default=False)
