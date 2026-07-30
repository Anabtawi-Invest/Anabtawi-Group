from collections import defaultdict

from odoo import _, api, Command, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare


class DirectSalesInvoiceLine(models.Model):
    _name = "direct.sales.invoice.line"
    _description = "Direct Sales Invoice Line"
    _inherit = ["analytic.mixin"]
    _order = "sequence, id"
    _check_company_auto = True

    sequence = fields.Integer(default=10)
    direct_invoice_id = fields.Many2one(
        "direct.sales.invoice", required=True, ondelete="cascade", index=True, check_company=True
    )
    state = fields.Selection(related="direct_invoice_id.state", store=True, index=True)
    product_id = fields.Many2one(
        "product.product",
        required=True,
        domain="[('sale_ok', '=', True), ('is_storable', '=', True)]",
        check_company=True,
        index=True,
    )
    name = fields.Text(string="Description")
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
        required=True,
    )
    quantity = fields.Float(
        string="Requested Quantity", default=1.0, required=True, digits="Product Unit"
    )
    approved_quantity = fields.Float(
        string="Approved Quantity", digits="Product Unit", copy=False
    )
    released_quantity = fields.Float(
        string="Released Quantity", digits="Product Unit", readonly=True, copy=False
    )
    on_hand_quantity = fields.Float(
        string="On Hand", compute="_compute_stock_quantities", digits="Product Unit"
    )
    available_quantity = fields.Float(
        string="Available in Warehouse",
        compute="_compute_stock_quantities",
        digits="Product Unit",
    )
    free_quantity = fields.Float(
        string="Free Quantity", compute="_compute_stock_quantities", digits="Product Unit"
    )
    reserved_quantity = fields.Float(
        string="Reserved Quantity",
        compute="_compute_stock_quantities",
        digits="Product Unit",
    )
    forecast_quantity = fields.Float(
        string="Forecast Quantity",
        compute="_compute_stock_quantities",
        digits="Product Unit",
    )
    incoming_quantity = fields.Float(
        string="Incoming Quantity",
        compute="_compute_stock_quantities",
        digits="Product Unit",
    )
    outgoing_quantity = fields.Float(
        string="Outgoing Quantity",
        compute="_compute_stock_quantities",
        digits="Product Unit",
    )
    shortage_quantity = fields.Float(
        string="Shortage", compute="_compute_stock_quantities", digits="Product Unit"
    )
    availability_state = fields.Selection(
        [
            ("available", "Available"),
            ("partial", "Partially Available"),
            ("unavailable", "Unavailable"),
        ],
        compute="_compute_stock_quantities",
        string="Availability",
    )
    price_unit = fields.Float(
        string="Unit Price", required=True, digits="Product Price"
    )
    original_pricelist_price = fields.Float(
        string="Original Pricelist Price",
        readonly=True,
        copy=True,
        digits="Product Price",
    )
    price_overridden = fields.Boolean(
        string="Price Manually Changed",
        compute="_compute_price_overridden",
        store=True,
        index=True,
    )
    price_override_reason = fields.Char(string="Price Override Reason", copy=True)
    price_override_state = fields.Selection(
        [
            ("none", "No Override"),
            ("pending", "Pending Approval"),
            ("approved", "Approved"),
        ],
        string="Price Override Approval",
        default="none",
        required=True,
        copy=False,
        index=True,
    )
    price_override_approved_by = fields.Many2one(
        "res.users",
        string="Price Override Approved By",
        readonly=True,
        copy=False,
    )
    discount = fields.Float(string="Discount %", digits="Discount")
    tax_ids = fields.Many2many(
        "account.tax",
        "direct_sales_invoice_line_tax_rel",
        "line_id",
        "tax_id",
        string="Taxes",
        check_company=True,
        domain="[('type_tax_use', '=', 'sale'), ('company_id', '=', company_id)]",
    )
    price_subtotal = fields.Monetary(
        compute="_compute_amount", store=True, currency_field="currency_id"
    )
    price_tax = fields.Monetary(
        compute="_compute_amount", store=True, currency_field="currency_id"
    )
    price_total = fields.Monetary(
        compute="_compute_amount", store=True, currency_field="currency_id"
    )
    currency_id = fields.Many2one(
        related="direct_invoice_id.currency_id", store=True
    )
    company_id = fields.Many2one(
        related="direct_invoice_id.company_id", store=True, index=True
    )
    lot_ids = fields.Many2many(
        "stock.lot",
        "direct_sales_invoice_line_lot_rel",
        "line_id",
        "lot_id",
        string="Released Lots",
        readonly=True,
        copy=False,
        check_company=True,
    )
    stock_move_ids = fields.One2many(
        "stock.move",
        "direct_invoice_line_id",
        string="Related Stock Moves",
        readonly=True,
        copy=False,
    )
    allocation_ids = fields.One2many(
        "direct.sales.invoice.allocation",
        "direct_invoice_line_id",
        string="Warehouse Allocations",
        copy=True,
    )
    warehouse_status = fields.Selection(
        [
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("partial", "Partially Approved"),
            ("rejected", "Rejected"),
            ("released", "Released"),
        ],
        default="pending",
        required=True,
        copy=False,
        index=True,
    )
    @api.constrains("discount")
    def _check_max_discount(self):
        for line in self:
            max_disc = line.company_id.direct_sales_max_discount_percent or 100.0
            if line.discount > max_disc:
                raise ValidationError(
                    _("Discount of %.2f%% exceeds maximum allowed discount of %.2f%%.")
                    % (line.discount, max_disc)
                )

    product_category_id = fields.Many2one(
        related="product_id.categ_id", store=True, index=True
    )
    partner_id = fields.Many2one(
        related="direct_invoice_id.partner_id", store=True, index=True
    )
    warehouse_id = fields.Many2one(
        related="direct_invoice_id.warehouse_id", store=True, index=True
    )
    user_id = fields.Many2one(
        related="direct_invoice_id.user_id", store=True, index=True
    )
    team_id = fields.Many2one(
        related="direct_invoice_id.team_id", store=True, index=True
    )
    pricelist_id = fields.Many2one(
        related="direct_invoice_id.pricelist_id", store=True, index=True
    )
    payment_term_id = fields.Many2one(
        related="direct_invoice_id.payment_term_id", store=True, index=True
    )
    payment_state = fields.Selection(
        related="direct_invoice_id.payment_state", store=True, index=True
    )
    invoice_date = fields.Date(
        related="direct_invoice_id.invoice_date", store=True, index=True
    )
    requested_date = fields.Datetime(
        related="direct_invoice_id.requested_date", store=True, index=True
    )
    is_cash_sale = fields.Boolean(
        related="direct_invoice_id.is_cash_sale", store=True, index=True
    )
    document_count = fields.Integer(
        string="Line Count",
        default=1,
        readonly=True,
        aggregator="sum",
    )

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals_list = []
        for incoming in vals_list:
            prepared = dict(incoming)
            prepared.update(
                {
                    "approved_quantity": 0.0,
                    "released_quantity": 0.0,
                    "warehouse_status": "pending",
                    "original_pricelist_price": 0.0,
                    "price_override_state": "none",
                    "price_override_approved_by": False,
                }
            )
            prepared.pop("lot_ids", None)
            product = self.env["product.product"].browse(prepared.get("product_id"))
            if product:
                prepared.setdefault("product_uom_id", product.uom_id.id)
                prepared.setdefault(
                    "name", product.get_product_multiline_description_sale()
                )
            # The expected pricelist value is computed after the line has its
            # document, company, currency and UoM.  Zero only satisfies the
            # required column during that initial ORM create.
            prepared.setdefault("price_unit", 0.0)
            prepared_vals_list.append(prepared)
        lines = super().create(prepared_vals_list)
        for line, incoming in zip(lines, vals_list):
            expected = line._get_pricelist_price()
            updates = {"original_pricelist_price": expected}
            if not incoming.get("name") and line.product_id:
                updates["name"] = line.product_id.get_product_multiline_description_sale()
            if not incoming.get("product_uom_id") and line.product_id:
                updates["product_uom_id"] = line.product_id.uom_id.id
            if "price_unit" not in incoming:
                updates.update({"price_unit": expected, "price_override_state": "none"})
            elif line.currency_id.compare_amounts(line.price_unit, expected):
                line._check_price_override_permission()
                if not incoming.get("price_override_reason"):
                    raise ValidationError(
                        _("A reason is required for every manual unit-price change.")
                    )
                updates["price_override_state"] = "pending"
            line.with_context(direct_sales_pricing_write=True).write(updates)
        return lines

    def write(self, vals):
        if {
            "approved_quantity",
            "released_quantity",
            "warehouse_status",
            "lot_ids",
        }.intersection(vals) and not self.env.context.get(
            "direct_sales_warehouse_write"
        ):
            raise AccessError(
                _(
                    "Approved, released, warehouse-status, and lot values are controlled "
                    "by warehouse workflow actions."
                )
            )
        if {
            "original_pricelist_price",
            "price_override_state",
            "price_override_approved_by",
        }.intersection(vals) and not (
            self.env.context.get("direct_sales_pricing_write")
            or self.env.context.get("direct_sales_price_approval")
        ):
            raise AccessError(
                _("Price audit fields can only be changed by pricing workflow actions.")
            )
        if (
            len(self) > 1
            and "price_unit" in vals
            and not self.env.context.get("direct_sales_pricing_write")
        ):
            for line in self:
                line.write(dict(vals))
            return True
        commercial_fields = {
            "product_id",
            "product_uom_id",
            "quantity",
            "price_unit",
            "discount",
            "tax_ids",
            "analytic_distribution",
        }
        if commercial_fields.intersection(vals) and not (
            self.env.context.get("direct_sales_pricing_write")
            or self.env.context.get("direct_sales_warehouse_write")
        ):
            if not (
                self.env.user.has_group("base.group_system")
                or self.env.user.has_group(
                    "anabtawi_direct_sales_invoice.group_direct_invoice_user"
                )
                or self.env.user.has_group(
                    "anabtawi_direct_sales_invoice.group_direct_invoice_sales_manager"
                )
                or self.env.user.has_group(
                    "anabtawi_direct_sales_invoice.group_direct_invoice_admin"
                )
            ):
                raise AccessError(
                    _("Only Direct Invoice commercial users may change product lines.")
                )
            if self.filtered(lambda line: line.direct_invoice_id.state != "draft"):
                raise UserError(
                    _(
                        "Product, quantity, price, discount, and tax values are frozen after submission."
                    )
                )
        if "price_unit" in vals and not self.env.context.get(
            "direct_sales_pricing_write"
        ):
            self._check_price_override_permission()
            self.ensure_one()
            expected = self._get_pricelist_price()
            vals = dict(vals)
            if self.currency_id.compare_amounts(vals["price_unit"], expected):
                reason = vals.get("price_override_reason") or self.price_override_reason
                if not reason:
                    raise ValidationError(
                        _("A reason is required for every manual unit-price change.")
                    )
                vals.update(
                    {
                        "price_override_state": "pending",
                        "price_override_approved_by": False,
                    }
                )
            else:
                vals.update(
                    {
                        "price_override_state": "none",
                        "price_override_reason": False,
                        "price_override_approved_by": False,
                    }
                )
        old_values = {
            line.id: (
                line.quantity,
                line.approved_quantity,
                line.price_unit,
            )
            for line in self
        }
        result = super().write(vals)
        if {"quantity", "approved_quantity", "price_unit"}.intersection(vals):
            for line in self:
                old_quantity, old_approved, old_price = old_values[line.id]
                changes = []
                if "quantity" in vals and old_quantity != line.quantity:
                    changes.append(
                        _("requested quantity %(old)s → %(new)s", old=old_quantity, new=line.quantity)
                    )
                if "approved_quantity" in vals and old_approved != line.approved_quantity:
                    changes.append(
                        _("approved quantity %(old)s → %(new)s", old=old_approved, new=line.approved_quantity)
                    )
                if "price_unit" in vals and old_price != line.price_unit:
                    changes.append(
                        _("unit price %(old)s → %(new)s", old=old_price, new=line.price_unit)
                    )
                if changes:
                    line.direct_invoice_id.message_post(
                        body=_(
                            "%(product)s: %(changes)s",
                            product=line.product_id.display_name,
                            changes=", ".join(changes),
                        )
                    )
        return result

    def unlink(self):
        if self.filtered(lambda line: line.direct_invoice_id.state != "draft"):
            raise UserError(_("Lines can only be deleted while the document is in Draft."))
        return super().unlink()

    def copy_data(self, default=None):
        default = dict(default or {})
        default.update(
            {
                "approved_quantity": 0.0,
                "released_quantity": 0.0,
                "warehouse_status": "pending",
                "price_override_state": "none",
                "price_override_approved_by": False,
                "lot_ids": [Command.clear()],
            }
        )
        return super().copy_data(default=default)

    def _check_price_override_permission(self):
        if self.env.context.get("direct_sales_price_approval"):
            return
        allowed = (
            self.env.user.has_group("base.group_system")
            or self.env.user.has_group(
                "anabtawi_direct_sales_invoice.group_direct_invoice_price_override"
            )
            or self.env.user.has_group(
                "anabtawi_direct_sales_invoice.group_direct_invoice_sales_manager"
            )
            or self.env.user.has_group(
                "anabtawi_direct_sales_invoice.group_direct_invoice_admin"
            )
        )
        if not allowed:
            raise AccessError(
                _(
                    "You are not allowed to change agreed customer prices. "
                    "Ask a user in 'Allow Direct Invoice Price Override'."
                )
            )

    def _get_pricelist_price(self):
        self.ensure_one()
        if not (
            self.direct_invoice_id.pricelist_id
            and self.product_id
            and self.product_uom_id
        ):
            return 0.0
        document = self.direct_invoice_id
        return document.pricelist_id.with_company(document.company_id)._get_product_price(
            self.product_id,
            self.quantity or 1.0,
            currency=document.currency_id,
            uom=self.product_uom_id,
            date=document.invoice_date or fields.Date.context_today(document),
        )

    def _recompute_pricelist_price(self, reset_override=False):
        for line in self:
            if not line.product_id or not line.product_uom_id:
                continue
            price = line._get_pricelist_price()
            values = {
                "original_pricelist_price": price,
                "price_unit": price,
            }
            if reset_override:
                values.update(
                    {
                        "price_override_reason": False,
                        "price_override_state": "none",
                        "price_override_approved_by": False,
                    }
                )
            line.with_context(direct_sales_pricing_write=True).update(values)

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for line in self:
            if not line.product_id:
                continue
            line.name = line.product_id.get_product_multiline_description_sale()
            line.product_uom_id = line.product_id.uom_id
            taxes = line.product_id.taxes_id._filter_taxes_by_company(line.company_id)
            if line.direct_invoice_id.fiscal_position_id:
                taxes = line.direct_invoice_id.fiscal_position_id.map_tax(taxes)
            line.tax_ids = taxes
            line._recompute_pricelist_price(reset_override=True)

    @api.onchange("quantity", "product_uom_id")
    def _onchange_pricing_inputs(self):
        for line in self:
            if line.direct_invoice_id.state == "draft":
                line._recompute_pricelist_price(reset_override=True)

    @api.depends(
        "quantity",
        "discount",
        "price_unit",
        "tax_ids",
        "currency_id",
        "product_id",
        "direct_invoice_id.partner_id",
    )
    def _compute_amount(self):
        for line in self:
            discounted_price = line.price_unit * (
                1.0 - (line.discount or 0.0) / 100.0
            )
            taxes = line.tax_ids.compute_all(
                discounted_price,
                currency=line.currency_id,
                quantity=line.quantity,
                product=line.product_id,
                partner=line.direct_invoice_id.partner_id,
            )
            line.price_subtotal = taxes["total_excluded"]
            line.price_total = taxes["total_included"]
            line.price_tax = taxes["total_included"] - taxes["total_excluded"]

    @api.depends("price_unit", "original_pricelist_price", "currency_id")
    def _compute_price_overridden(self):
        for line in self:
            line.price_overridden = bool(
                line.currency_id
                and line.currency_id.compare_amounts(
                    line.price_unit, line.original_pricelist_price
                )
            )

    @api.depends(
        "product_id",
        "product_uom_id",
        "quantity",
        "direct_invoice_id.source_location_id",
        "direct_invoice_id.company_id",
    )
    def _compute_stock_quantities(self):
        grouped = defaultdict(lambda: self.env["direct.sales.invoice.line"])
        for line in self:
            location = line.direct_invoice_id.source_location_id
            company = line.direct_invoice_id.company_id
            if line.product_id and location and company:
                grouped[(location.id, company.id)] |= line
            else:
                line._set_empty_stock_quantities()
        for (location_id, company_id), lines in grouped.items():
            products = lines.product_id.with_context(
                location=location_id, allowed_company_ids=[company_id]
            )
            products.fetch(
                [
                    "qty_available",
                    "free_qty",
                    "virtual_available",
                    "incoming_qty",
                    "outgoing_qty",
                ]
            )
            products_by_id = {product.id: product for product in products}
            for line in lines:
                product = products_by_id[line.product_id.id]
                on_hand = product.uom_id._compute_quantity(
                    product.qty_available, line.product_uom_id, round=False
                )
                free = product.uom_id._compute_quantity(
                    product.free_qty, line.product_uom_id, round=False
                )
                forecast = product.uom_id._compute_quantity(
                    product.virtual_available, line.product_uom_id, round=False
                )
                incoming = product.uom_id._compute_quantity(
                    product.incoming_qty, line.product_uom_id, round=False
                )
                outgoing = product.uom_id._compute_quantity(
                    product.outgoing_qty, line.product_uom_id, round=False
                )
                line.on_hand_quantity = on_hand
                line.available_quantity = free
                line.free_quantity = free
                line.reserved_quantity = max(on_hand - free, 0.0)
                line.forecast_quantity = forecast
                line.incoming_quantity = incoming
                line.outgoing_quantity = outgoing
                line.shortage_quantity = max(line.quantity - free, 0.0)
                if float_compare(
                    free,
                    line.quantity,
                    precision_rounding=line.product_uom_id.rounding,
                ) >= 0:
                    line.availability_state = "available"
                elif float_compare(
                    free, 0.0, precision_rounding=line.product_uom_id.rounding
                ) > 0:
                    line.availability_state = "partial"
                else:
                    line.availability_state = "unavailable"

    def _set_empty_stock_quantities(self):
        for line in self:
            line.on_hand_quantity = 0.0
            line.available_quantity = 0.0
            line.free_quantity = 0.0
            line.reserved_quantity = 0.0
            line.forecast_quantity = 0.0
            line.incoming_quantity = 0.0
            line.outgoing_quantity = 0.0
            line.shortage_quantity = max(line.quantity, 0.0)
            line.availability_state = "unavailable"

    @api.constrains("quantity", "approved_quantity", "released_quantity")
    def _check_quantities(self):
        for line in self:
            rounding = line.product_uom_id.rounding
            if float_compare(line.quantity, 0.0, precision_rounding=rounding) <= 0:
                raise ValidationError(_("Requested quantity must be greater than zero."))
            if float_compare(
                line.approved_quantity, 0.0, precision_rounding=rounding
            ) < 0:
                raise ValidationError(_("Approved quantity cannot be negative."))
            if float_compare(
                line.approved_quantity, line.quantity, precision_rounding=rounding
            ) > 0:
                raise ValidationError(
                    _("Approved quantity cannot exceed requested quantity.")
                )
            if float_compare(
                line.released_quantity,
                line.approved_quantity,
                precision_rounding=rounding,
            ) > 0:
                raise ValidationError(
                    _("Released quantity cannot exceed approved quantity.")
                )

    @api.constrains(
        "price_unit",
        "original_pricelist_price",
        "price_override_reason",
        "price_override_state",
    )
    def _check_price_override_reason(self):
        for line in self:
            if (
                line.price_overridden
                and line.direct_invoice_id.company_id.direct_sales_price_override_approval
                and not line.price_override_reason
            ):
                raise ValidationError(
                    _("A reason is required for every manual price override.")
                )

    @api.constrains("discount")
    def _check_discount(self):
        for line in self:
            if line.discount < 0 or line.discount > 100:
                raise ValidationError(_("Discount must be between 0 and 100 percent."))
