from collections import defaultdict

from odoo import _, api, Command, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero


DIRECT_SALES_STATES = [
    ("draft", "Draft"),
    ("warehouse_pending", "Waiting Warehouse Approval"),
    ("partially_approved", "Partially Approved"),
    ("warehouse_approved", "Warehouse Approved"),
    ("ready", "Ready for Pickup"),
    ("released", "Goods Released"),
    ("completed", "Completed"),
    ("rejected", "Rejected"),
    ("cancelled", "Cancelled"),
]


class DirectSalesInvoice(models.Model):
    _name = "direct.sales.invoice"
    _description = "Direct Sales Invoice"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "requested_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(
        string="Direct Invoice Reference",
        required=True,
        copy=False,
        readonly=True,
        default="New",
        index="trigram",
        tracking=True,
    )
    active = fields.Boolean(default=True)
    state = fields.Selection(
        DIRECT_SALES_STATES,
        default="draft",
        required=True,
        copy=False,
        tracking=True,
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        required=True,
        tracking=True,
        check_company=True,
        index=True,
    )
    commercial_partner_id = fields.Many2one(
        "res.partner",
        related="partner_id.commercial_partner_id",
        store=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
        index=True,
    )
    company_currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
    )
    currency_id = fields.Many2one(
        "res.currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
        tracking=True,
    )
    pricelist_id = fields.Many2one(
        "product.pricelist",
        string="Pricelist Used",
        required=True,
        tracking=True,
        copy=True,
        check_company=True,
        domain="[('company_id', 'in', [company_id, False])]",
        index=True,
    )
    allowed_warehouse_ids = fields.Many2many(
        "stock.warehouse",
        compute="_compute_allowed_warehouse_ids",
        string="Permitted Warehouses",
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Pickup Warehouse",
        required=True,
        tracking=True,
        copy=True,
        check_company=True,
        domain="[('id', 'in', allowed_warehouse_ids)]",
        index=True,
    )
    source_location_id = fields.Many2one(
        "stock.location",
        string="Source Stock Location",
        required=True,
        tracking=True,
        copy=True,
        check_company=True,
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [company_id, False])]",
    )
    dispatch_location_id = fields.Many2one(
        "stock.location",
        string="Digital Dispatch Location",
        tracking=True,
        copy=True,
        check_company=True,
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [company_id, False])]",
    )
    stock_flow = fields.Selection(
        [
            ("direct_delivery", "Direct Delivery"),
            ("dispatch_then_customer", "Dispatch then Customer"),
        ],
        string="Stock Flow",
        required=True,
        default="dispatch_then_customer",
        copy=True,
        tracking=True,
    )
    payment_term_id = fields.Many2one(
        "account.payment.term",
        string="Payment Terms",
        tracking=True,
        copy=True,
        check_company=True,
    )
    fiscal_position_id = fields.Many2one(
        "account.fiscal.position",
        string="Fiscal Position",
        copy=True,
        check_company=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Salesperson",
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
        index=True,
    )
    team_id = fields.Many2one(
        "crm.team",
        string="Sales Team",
        tracking=True,
        copy=True,
        check_company=True,
        index=True,
    )
    invoice_date = fields.Date(
        string="Invoice Date",
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )
    requested_date = fields.Datetime(
        string="Requested Date",
        default=fields.Datetime.now,
        required=True,
        readonly=True,
        copy=False,
        index=True,
    )
    ready_date = fields.Datetime(
        string="Ready Date",
        readonly=True,
        copy=False,
        index=True,
    )
    warehouse_approved_by = fields.Many2one(
        "res.users",
        string="Warehouse Approved By",
        readonly=True,
        copy=False,
        tracking=True,
    )
    warehouse_approved_at = fields.Datetime(
        string="Warehouse Approval Date",
        readonly=True,
        copy=False,
        tracking=True,
    )
    released_by = fields.Many2one(
        "res.users",
        string="Released By",
        readonly=True,
        copy=False,
        tracking=True,
    )
    released_at = fields.Datetime(
        string="Release Date",
        readonly=True,
        copy=False,
        tracking=True,
        index=True,
    )
    customer_receiver_name = fields.Char(
        string="Customer Receiver",
        readonly=True,
        copy=False,
    )
    rejection_reason = fields.Text(
        string="Rejection Reason",
        readonly=True,
        copy=False,
        tracking=True,
    )
    notes = fields.Text(string="Internal Notes", copy=True)
    customer_note = fields.Text(string="Customer Note", copy=True)
    warehouse_comment = fields.Text(string="Warehouse Comment", copy=False)

    line_ids = fields.One2many(
        "direct.sales.invoice.line",
        "direct_invoice_id",
        string="Products",
        copy=True,
    )
    allocation_ids = fields.One2many(
        "direct.sales.invoice.allocation",
        "direct_invoice_id",
        string="Warehouse Allocations",
        copy=True,
    )
    picking_ids = fields.One2many(
        "stock.picking",
        "direct_invoice_id",
        string="Related Pickings",
        readonly=True,
        copy=False,
    )
    picking_count = fields.Integer(compute="_compute_counts")
    stock_move_count = fields.Integer(compute="_compute_counts")
    approval_count = fields.Integer(compute="_compute_counts")
    attachment_count = fields.Integer(compute="_compute_counts")
    payment_count = fields.Integer(compute="_compute_payment_count")
    invoice_id = fields.Many2one(
        "account.move",
        string="Customer Invoice",
        readonly=True,
        copy=False,
        check_company=True,
        index=True,
    )
    invoice_count = fields.Integer(compute="_compute_counts")
    invoice_status = fields.Selection(
        [
            ("none", "Not Created"),
            ("draft", "Draft"),
            ("posted", "Posted"),
            ("cancel", "Cancelled"),
        ],
        compute="_compute_invoice_status",
        store=True,
        index=True,
    )
    payment_state = fields.Selection(
        related="invoice_id.payment_state",
        string="Payment Status",
        store=True,
        index=True,
    )
    amount_residual = fields.Monetary(
        related="invoice_id.amount_residual",
        string="Amount Due",
        currency_field="currency_id",
        store=True,
    )
    due_date = fields.Date(
        related="invoice_id.invoice_date_due",
        string="Due Date",
        store=True,
        index=True,
    )
    amount_paid = fields.Monetary(
        compute="_compute_amount_paid",
        string="Paid Amount",
        currency_field="currency_id",
        store=True,
    )
    amount_untaxed = fields.Monetary(
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
    )
    amount_tax = fields.Monetary(
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
    )
    amount_total = fields.Monetary(
        compute="_compute_amounts",
        store=True,
        currency_field="currency_id",
    )
    is_cash_sale = fields.Boolean(
        string="Cash Sale",
        tracking=True,
        copy=True,
        help="Enable for a sale that must be settled immediately rather than on credit terms.",
    )
    payment_clearance_required = fields.Boolean(
        compute="_compute_payment_clearance",
        string="Payment Clearance Required",
    )
    payment_cleared = fields.Boolean(
        compute="_compute_payment_clearance",
        string="Payment Cleared",
    )
    manual_price_override = fields.Boolean(
        compute="_compute_commercial_flags",
        store=True,
        index=True,
    )
    price_override_count = fields.Integer(
        compute="_compute_commercial_flags",
        store=True,
    )
    product_count = fields.Integer(compute="_compute_line_statistics", store=True)
    requested_quantity = fields.Float(
        compute="_compute_line_statistics",
        store=True,
        string="Requested Quantity",
    )
    approved_quantity = fields.Float(
        compute="_compute_line_statistics",
        store=True,
        string="Approved Quantity",
    )
    released_quantity = fields.Float(
        compute="_compute_line_statistics",
        store=True,
        string="Released Quantity",
    )
    available_status = fields.Selection(
        [
            ("available", "Available"),
            ("partial", "Partially Available"),
            ("unavailable", "Unavailable"),
        ],
        compute="_compute_available_status",
        string="Stock Status",
    )
    document_count = fields.Integer(
        string="Document Count",
        default=1,
        readonly=True,
        aggregator="sum",
    )
    partial_approval_count = fields.Integer(
        string="Partial Approval Count",
        compute="_compute_outcome_counts",
        store=True,
        aggregator="sum",
    )
    rejection_count = fields.Integer(
        string="Rejection Count",
        compute="_compute_outcome_counts",
        store=True,
        aggregator="sum",
    )

    _name_company_uniq = models.Constraint(
        "UNIQUE(name, company_id)",
        "The direct invoice reference must be unique per company.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.update(
                {
                    "state": "draft",
                    "warehouse_approved_by": False,
                    "warehouse_approved_at": False,
                    "released_by": False,
                    "released_at": False,
                    "ready_date": False,
                    "customer_receiver_name": False,
                    "rejection_reason": False,
                    "invoice_id": False,
                    "requested_date": fields.Datetime.now(),
                }
            )
            vals.pop("picking_ids", None)
            company = self.env["res.company"].browse(
                vals.get("company_id")
            ) or self.env.company
            if vals.get("name", "New") == "New":
                vals["name"] = (
                    self.env["ir.sequence"]
                    .with_company(company)
                    .next_by_code("direct.sales.invoice")
                    or _("New")
                )
            partner = self.env["res.partner"].browse(vals.get("partner_id"))
            if partner:
                customer_pricelist = (
                    partner.with_company(company).property_product_pricelist
                )
                if (
                    vals.get("pricelist_id")
                    and vals["pricelist_id"] != customer_pricelist.id
                    and not (
                        self.env.user.has_group("base.group_system")
                        or self.env.user.has_group(
                            "anabtawi_direct_sales_invoice.group_direct_invoice_sales_manager"
                        )
                        or self.env.user.has_group(
                            "anabtawi_direct_sales_invoice.group_direct_invoice_admin"
                        )
                    )
                ):
                    raise AccessError(
                        _(
                            "Only a Direct Invoice Sales Manager may replace the "
                            "customer's assigned pricelist."
                        )
                    )
                vals.setdefault(
                    "pricelist_id",
                    customer_pricelist.id,
                )
                pricelist = self.env["product.pricelist"].browse(
                    vals.get("pricelist_id")
                )
                vals["currency_id"] = (
                    pricelist.currency_id.id or company.currency_id.id
                )
                vals.setdefault(
                    "payment_term_id",
                    (
                        partner.with_company(company).property_payment_term_id
                        or company.direct_sales_default_payment_term_id
                    ).id,
                )
                vals.setdefault(
                    "fiscal_position_id",
                    self.env["account.fiscal.position"]
                    .with_company(company)
                    ._get_fiscal_position(partner)
                    .id,
                )
            warehouse = self.env["stock.warehouse"].browse(vals.get("warehouse_id"))
            if warehouse:
                vals["source_location_id"] = warehouse.lot_stock_id.id
                vals["dispatch_location_id"] = (
                    warehouse.direct_sales_dispatch_location_id.id
                )
                vals["stock_flow"] = warehouse.direct_sales_stock_flow
            requested_user_id = vals.get("user_id", self.env.user.id)
            if requested_user_id != self.env.user.id and not (
                self.env.user.has_group("base.group_system")
                or self.env.user.has_group(
                    "anabtawi_direct_sales_invoice.group_direct_invoice_sales_manager"
                )
                or self.env.user.has_group(
                    "anabtawi_direct_sales_invoice.group_direct_invoice_admin"
                )
            ):
                raise AccessError(
                    _("Only a Direct Invoice Sales Manager may assign another salesperson.")
                )
        records = super().create(vals_list)
        records._check_user_warehouse_assignment()
        return records

    def write(self, vals):
        if len(self) > 1 and {"partner_id", "pricelist_id", "warehouse_id"}.intersection(
            vals
        ):
            for record in self:
                record.write(dict(vals))
            return True
        vals = dict(vals)
        pricing_changed = bool({"partner_id", "pricelist_id"}.intersection(vals))
        if "partner_id" in vals:
            self.ensure_one()
            partner = self.env["res.partner"].browse(vals["partner_id"]).with_company(
                self.company_id
            )
            customer_pricelist = partner.property_product_pricelist
            if not self._can_manage_commercial_terms():
                if (
                    vals.get("pricelist_id")
                    and vals["pricelist_id"] != customer_pricelist.id
                ):
                    raise AccessError(
                        _(
                            "Only a Direct Invoice Sales Manager may replace the "
                            "customer's assigned pricelist."
                        )
                    )
                vals["pricelist_id"] = customer_pricelist.id
            else:
                vals.setdefault("pricelist_id", customer_pricelist.id)
            selected_pricelist = self.env["product.pricelist"].browse(
                vals["pricelist_id"]
            )
            vals["currency_id"] = selected_pricelist.currency_id.id
            vals.setdefault(
                "payment_term_id",
                (
                    partner.property_payment_term_id
                    or self.company_id.direct_sales_default_payment_term_id
                ).id,
            )
            vals.setdefault(
                "fiscal_position_id",
                self.env["account.fiscal.position"]
                .with_company(self.company_id)
                ._get_fiscal_position(partner)
                .id,
            )
        elif "pricelist_id" in vals:
            vals["currency_id"] = self.env["product.pricelist"].browse(
                vals["pricelist_id"]
            ).currency_id.id
        if "warehouse_id" in vals:
            warehouse = self.env["stock.warehouse"].browse(vals["warehouse_id"])
            if (
                not self._is_direct_administrator()
                and warehouse not in self._get_permitted_warehouses()
            ):
                raise AccessError(
                    _(
                        "You are not assigned to direct sales warehouse %s.",
                        warehouse.display_name,
                    )
                )
            vals.update(
                {
                    "source_location_id": warehouse.lot_stock_id.id,
                    "dispatch_location_id": (
                        warehouse.direct_sales_dispatch_location_id.id
                    ),
                    "stock_flow": warehouse.direct_sales_stock_flow,
                }
            )
        protected = {
            "partner_id",
            "company_id",
            "currency_id",
            "pricelist_id",
            "warehouse_id",
            "source_location_id",
            "dispatch_location_id",
            "stock_flow",
            "payment_term_id",
            "fiscal_position_id",
            "user_id",
            "team_id",
            "invoice_date",
            "is_cash_sale",
        }
        if protected.intersection(vals) and not self.env.context.get(
            "direct_sales_bypass_lock"
        ):
            self._check_sales_user()
            locked = self.filtered(lambda record: record.state != "draft")
            if locked:
                raise UserError(
                    _(
                        "Customer, warehouse, pricing, and accounting terms are frozen "
                        "after submission. Reset the document to Draft before changing them."
                    )
                )
        workflow_fields = {
            "state",
            "warehouse_approved_by",
            "warehouse_approved_at",
            "released_by",
            "released_at",
            "ready_date",
            "customer_receiver_name",
            "rejection_reason",
            "invoice_id",
            "requested_date",
        }
        if workflow_fields.intersection(vals) and not self.env.context.get(
            "direct_sales_bypass_lock"
        ):
            raise AccessError(
                _(
                    "Workflow, approval, release, and invoice links can only be changed "
                    "through the Direct Sales actions."
                )
            )
        if "pricelist_id" in vals and not self.env.context.get(
            "direct_sales_bypass_pricelist_security"
        ):
            partner_change_to_assigned_pricelist = (
                "partner_id" in vals
                and self.env["res.partner"]
                .browse(vals["partner_id"])
                .with_company(self.company_id)
                .property_product_pricelist.id
                == vals["pricelist_id"]
            )
            if (
                not self._can_manage_commercial_terms()
                and not partner_change_to_assigned_pricelist
            ):
                raise AccessError(
                    _("Only a Direct Invoice Sales Manager may change the pricelist.")
                )
        result = super().write(vals)
        if "warehouse_id" in vals:
            self._check_user_warehouse_assignment()
        if pricing_changed:
            self.line_ids._recompute_pricelist_price(reset_override=True)
        return result

    def unlink(self):
        for record in self:
            if record.state != "draft" or record.picking_ids or record.invoice_id:
                raise UserError(
                    _(
                        "Only untouched Draft direct invoices may be deleted. "
                        "Cancel processed documents to preserve their audit trail."
                    )
                )
        return super().unlink()

    def copy_data(self, default=None):
        default = dict(default or {})
        default.update(
            {
                "name": "New",
                "state": "draft",
                "warehouse_approved_by": False,
                "warehouse_approved_at": False,
                "released_by": False,
                "released_at": False,
                "ready_date": False,
                "customer_receiver_name": False,
                "rejection_reason": False,
                "warehouse_comment": False,
                "invoice_id": False,
            }
        )
        return super().copy_data(default=default)

    @api.depends("line_ids.price_subtotal", "line_ids.price_tax", "line_ids.price_total")
    def _compute_amounts(self):
        for record in self:
            record.amount_untaxed = sum(record.line_ids.mapped("price_subtotal"))
            record.amount_tax = sum(record.line_ids.mapped("price_tax"))
            record.amount_total = sum(record.line_ids.mapped("price_total"))

    @api.depends("invoice_id", "invoice_id.state")
    def _compute_invoice_status(self):
        for record in self:
            record.invoice_status = record.invoice_id.state if record.invoice_id else "none"

    @api.depends("invoice_id.amount_total", "invoice_id.amount_residual", "invoice_id.state")
    def _compute_amount_paid(self):
        for record in self:
            if record.invoice_id and record.invoice_id.state == "posted":
                record.amount_paid = max(
                    record.invoice_id.amount_total - record.invoice_id.amount_residual,
                    0.0,
                )
            else:
                record.amount_paid = 0.0

    @api.depends("is_cash_sale", "payment_state", "company_id.cash_customer_release_policy")
    def _compute_payment_clearance(self):
        for record in self:
            record.payment_clearance_required = bool(
                record.is_cash_sale
                and record.company_id.cash_customer_release_policy == "require_payment"
            )
            record.payment_cleared = bool(
                not record.payment_clearance_required or record.payment_state == "paid"
            )

    @api.depends("line_ids.price_overridden")
    def _compute_commercial_flags(self):
        for record in self:
            overridden = record.line_ids.filtered("price_overridden")
            record.manual_price_override = bool(overridden)
            record.price_override_count = len(overridden)

    @api.depends(
        "line_ids.product_id",
        "line_ids.quantity",
        "line_ids.approved_quantity",
        "line_ids.released_quantity",
    )
    def _compute_line_statistics(self):
        for record in self:
            record.product_count = len(record.line_ids)
            record.requested_quantity = sum(record.line_ids.mapped("quantity"))
            record.approved_quantity = sum(record.line_ids.mapped("approved_quantity"))
            record.released_quantity = sum(record.line_ids.mapped("released_quantity"))

    @api.depends("line_ids.availability_state")
    def _compute_available_status(self):
        for record in self:
            states = set(record.line_ids.mapped("availability_state"))
            if not states or states == {"available"}:
                record.available_status = "available"
            elif states == {"unavailable"}:
                record.available_status = "unavailable"
            else:
                record.available_status = "partial"

    @api.depends("state")
    def _compute_outcome_counts(self):
        for record in self:
            record.partial_approval_count = int(record.state == "partially_approved")
            record.rejection_count = int(record.state == "rejected")

    def _compute_counts(self):
        Approval = self.env["direct.sales.invoice.approval"]
        Attachment = self.env["ir.attachment"]
        record_ids = [record.id for record in self if isinstance(record.id, int)]
        approval_counts = {
            document.id: count
            for document, count in Approval._read_group(
                [("direct_invoice_id", "in", record_ids)],
                ["direct_invoice_id"],
                ["__count"],
            )
        } if record_ids else {}
        attachment_counts = {
            res_id: count
            for res_id, count in Attachment._read_group(
                [
                    ("res_model", "=", self._name),
                    ("res_id", "in", record_ids),
                ],
                ["res_id"],
                ["__count"],
            )
        } if record_ids else {}
        for record in self:
            record.picking_count = len(record.picking_ids)
            record.stock_move_count = len(record.picking_ids.move_ids)
            record.invoice_count = 1 if record.invoice_id else 0
            record.approval_count = approval_counts.get(record.id, 0)
            record.attachment_count = attachment_counts.get(record.id, 0)

    def _compute_payment_count(self):
        for record in self:
            payments = (
                record.invoice_id._get_reconciled_payments()
                if record.invoice_id and record.invoice_id.state == "posted"
                else self.env["account.payment"]
            )
            record.payment_count = len(payments)

    @api.onchange("partner_id", "company_id")
    def _onchange_partner_id(self):
        for record in self:
            if not record.partner_id:
                continue
            partner = record.partner_id.with_company(record.company_id)
            pricelist = partner.property_product_pricelist
            warning = False
            if record.line_ids.filtered("price_overridden"):
                warning = {
                    "title": _("Manual prices will be recalculated"),
                    "message": _(
                        "Changing the customer replaces existing manual prices with "
                        "prices from the new customer's pricelist."
                    ),
                }
            record.pricelist_id = pricelist
            record.currency_id = pricelist.currency_id or record.company_id.currency_id
            record.payment_term_id = (
                partner.property_payment_term_id
                or record.company_id.direct_sales_default_payment_term_id
            )
            record.fiscal_position_id = (
                self.env["account.fiscal.position"]
                .with_company(record.company_id)
                ._get_fiscal_position(partner)
            )
            for line in record.line_ids:
                line._recompute_pricelist_price(reset_override=True)
            if warning:
                return {"warning": warning}

    @api.onchange("pricelist_id")
    def _onchange_pricelist_id(self):
        for record in self:
            if record.pricelist_id:
                record.currency_id = record.pricelist_id.currency_id
                for line in record.line_ids:
                    line._recompute_pricelist_price(reset_override=True)

    @api.onchange("warehouse_id")
    def _onchange_warehouse_id(self):
        for record in self:
            warehouse = record.warehouse_id
            if not warehouse:
                record.source_location_id = False
                record.dispatch_location_id = False
                continue
            record.source_location_id = warehouse.lot_stock_id
            record.dispatch_location_id = warehouse.direct_sales_dispatch_location_id
            record.stock_flow = warehouse.direct_sales_stock_flow

    @api.depends_context("uid", "allowed_company_ids")
    @api.depends("company_id")
    def _compute_allowed_warehouse_ids(self):
        for record in self:
            record.allowed_warehouse_ids = record._get_permitted_warehouses()

    def _get_permitted_warehouses(self):
        self.ensure_one()
        domain = [
            ("direct_sales_enabled", "=", True),
            ("company_id", "=", self.company_id.id),
        ]
        if self._is_direct_administrator():
            return self.env["stock.warehouse"].search(domain)
        user = self.env.user
        permitted = (
            user.direct_sales_warehouse_ids
            | user.direct_sales_approval_warehouse_ids
        ).filtered(
            lambda warehouse: warehouse.direct_sales_enabled
            and warehouse.company_id == self.company_id
        )
        # Compatibility with the installed Anabtawi warehouse restriction add-on,
        # without introducing a hard dependency on that optional module.
        if (
            "restrict_ware_house" in user._fields
            and user.restrict_ware_house
            and "allowed_ware_house_ids" in user._fields
        ):
            permitted &= user.allowed_ware_house_ids
        return permitted

    @api.constrains("warehouse_id", "source_location_id", "dispatch_location_id")
    def _check_warehouse_locations(self):
        for record in self:
            if (
                record.source_location_id
                and not record.warehouse_id._direct_sales_contains_location(
                    record.source_location_id
                )
            ):
                raise ValidationError(
                    _("The source location must belong to the selected pickup warehouse.")
                )
            if (
                record.stock_flow == "dispatch_then_customer"
                and record.dispatch_location_id
                and not record.warehouse_id._direct_sales_contains_location(
                    record.dispatch_location_id
                )
            ):
                raise ValidationError(
                    _("The dispatch location must belong to the selected pickup warehouse.")
                )

    def _is_direct_administrator(self):
        return self.env.user.has_group(
            "anabtawi_direct_sales_invoice.group_direct_invoice_admin"
        ) or self.env.user.has_group("base.group_system")

    def _can_manage_commercial_terms(self):
        return self._is_direct_administrator() or self.env.user.has_group(
            "anabtawi_direct_sales_invoice.group_direct_invoice_sales_manager"
        )

    def _check_warehouse_manager(self):
        if not (
            self._is_direct_administrator()
            or self.env.user.has_group(
                "anabtawi_direct_sales_invoice.group_direct_invoice_warehouse_manager"
            )
        ):
            raise AccessError(
                _("Only a Direct Invoice Warehouse Manager may perform this action.")
            )

    def _check_warehouse_user(self):
        if not (
            self._is_direct_administrator()
            or self.env.user.has_group(
                "anabtawi_direct_sales_invoice.group_direct_invoice_warehouse_user"
            )
            or self.env.user.has_group(
                "anabtawi_direct_sales_invoice.group_direct_invoice_warehouse_manager"
            )
        ):
            raise AccessError(
                _("Only an assigned Direct Invoice Warehouse user may perform this action.")
            )

    def _check_sales_user(self):
        if not (
            self._is_direct_administrator()
            or self.env.user.has_group(
                "anabtawi_direct_sales_invoice.group_direct_invoice_user"
            )
            or self.env.user.has_group(
                "anabtawi_direct_sales_invoice.group_direct_invoice_sales_manager"
            )
        ):
            raise AccessError(_("You are not allowed to submit direct invoices."))

    def _check_user_warehouse_assignment(self):
        for record in self:
            if self._is_direct_administrator():
                continue
            document_warehouses = record.warehouse_id
            if record.company_id.allow_multi_warehouse_fulfillment:
                document_warehouses |= record.allocation_ids.warehouse_id
            unauthorized = document_warehouses - record._get_permitted_warehouses()
            if unauthorized:
                raise AccessError(
                    _(
                        "You are not assigned to every source warehouse on this direct "
                        "invoice: %s.",
                        ", ".join(unauthorized.mapped("display_name")),
                    )
                )

    def _log_approval_event(self, event, note=None, state_from=None, state_to=None):
        values = []
        for record in self:
            values.append(
                {
                    "direct_invoice_id": record.id,
                    "event": event,
                    "user_id": self.env.user.id,
                    "event_date": fields.Datetime.now(),
                    "state_from": state_from or record.state,
                    "state_to": state_to or record.state,
                    "note": note,
                    "quantity_snapshot": "\n".join(
                        _(
                            "%(product)s: requested %(requested)s, approved "
                            "%(approved)s, released %(released)s",
                            product=line.product_id.display_name,
                            requested=line.quantity,
                            approved=line.approved_quantity,
                            released=line.released_quantity,
                        )
                        for line in record.line_ids
                    ),
                }
            )
        return self.env["direct.sales.invoice.approval"].sudo().create(values)

    def _schedule_activity_once(self, activity_xmlid, users, summary, note=None):
        activity_type = self.env.ref(activity_xmlid)
        for record in self:
            for user in users:
                existing = record.activity_ids.filtered(
                    lambda activity: activity.activity_type_id == activity_type
                    and activity.user_id == user
                )
                if not existing:
                    record.activity_schedule(
                        activity_xmlid,
                        user_id=user.id,
                        summary=summary,
                        note=note,
                    )

    def _complete_activities(self, activity_xmlid):
        activity_type = self.env.ref(activity_xmlid)
        activities = self.mapped("activity_ids").filtered(
            lambda activity: activity.activity_type_id == activity_type
        )
        if activities:
            activities.sudo().action_done()

    def _notify_users(self, users, body):
        partners = users.mapped("partner_id")
        for record in self:
            record.message_post(
                body=body,
                partner_ids=partners.ids,
                subtype_xmlid="mail.mt_note",
            )

    def _schedule_payment_collection(self, summary=None):
        activity_type = self.env.ref(
            "anabtawi_direct_sales_invoice.mail_activity_direct_payment_collection"
        )
        accounting_group = self.env.ref(
            "anabtawi_direct_sales_invoice.group_direct_invoice_accounting_user"
        )
        for record in self:
            accounting_users = accounting_group.user_ids.filtered(
                lambda user: record.company_id in user.company_ids
            )
            responsible_users = accounting_users or record.user_id
            created_for = self.env["res.users"]
            for user in responsible_users:
                existing = record.activity_ids.filtered(
                    lambda activity: activity.activity_type_id == activity_type
                    and activity.user_id == user
                )
                if not existing:
                    record.activity_schedule(
                        activity_type_id=activity_type.id,
                        user_id=user.id,
                        summary=summary or _("Collect payment for %s", record.name),
                        note=_(
                            "Invoice: %(invoice)s\nOutstanding: %(amount)s %(currency)s",
                            invoice=record.invoice_id.display_name,
                            amount=record.amount_residual,
                            currency=record.currency_id.name,
                        ),
                    )
                    created_for |= user
            if created_for:
                record._notify_users(
                    created_for,
                    _(
                        "Payment follow-up is required for direct invoice "
                        "<b>%(reference)s</b>.",
                        reference=record.name,
                    ),
                )

    @api.model
    def _cron_schedule_payment_followups(self):
        activity_type = self.env.ref(
            "anabtawi_direct_sales_invoice.mail_activity_direct_payment_collection"
        )
        settled = self.search(
            [
                ("invoice_id.state", "=", "posted"),
                ("amount_residual", "<=", 0),
            ]
        )
        settled_activities = settled.mapped("activity_ids").filtered(
            lambda activity: activity.activity_type_id == activity_type
        )
        if settled_activities:
            settled_activities.sudo().action_done()

        today = fields.Date.context_today(self)
        overdue = self.search(
            [
                ("company_id.direct_sales_enabled", "=", True),
                ("invoice_id.state", "=", "posted"),
                ("amount_residual", ">", 0),
                ("due_date", "!=", False),
                ("due_date", "<", today),
                ("state", "in", ("released", "completed")),
            ]
        )
        overdue._schedule_payment_collection(
            summary=_("Overdue direct invoice payment")
        )
        return True

    def _validate_submission(self):
        for record in self:
            if record.state != "draft":
                raise UserError(_("Only Draft direct invoices can be submitted."))
            if not record.company_id.direct_sales_enabled:
                raise UserError(
                    _("Direct Sales Invoice is not enabled for company %s.", record.company_id.display_name)
                )
            if not record.partner_id:
                raise UserError(_("Select a customer before submission."))
            if not record.warehouse_id or not record.warehouse_id.direct_sales_enabled:
                raise UserError(_("Select an enabled pickup warehouse."))
            if not record.pricelist_id:
                raise UserError(_("The customer does not have an applicable pricelist."))
            if not record.line_ids:
                raise UserError(_("Add at least one product line."))
            if any(line.quantity <= 0 for line in record.line_ids):
                raise UserError(_("Every requested quantity must be greater than zero."))
            unapproved_overrides = record.line_ids.filtered(
                lambda line: line.price_overridden
                and (
                    not line.price_override_reason
                    or (
                        record.company_id.direct_sales_price_override_approval
                        and line.price_override_state != "approved"
                    )
                )
            )
            if unapproved_overrides:
                raise UserError(
                    _(
                        "Every manual price requires a reason and Sales Manager approval "
                        "before warehouse submission."
                    )
                )
            if record.stock_flow == "dispatch_then_customer":
                if not record.dispatch_location_id:
                    raise UserError(
                        _("Configure a Direct Sales Dispatch Location on the warehouse.")
                    )
                if not record.warehouse_id.direct_sales_operation_type_id:
                    raise UserError(
                        _("Configure a Direct Sales Preparation Operation Type on the warehouse.")
                    )
            record._validate_allocations()

    def action_submit_to_warehouse(self):
        self._check_sales_user()
        self._check_user_warehouse_assignment()
        self._validate_submission()
        for record in self:
            approval_warehouses = record.warehouse_id
            if record.company_id.allow_multi_warehouse_fulfillment:
                approval_warehouses |= record.allocation_ids.warehouse_id
            warehouses_without_approvers = approval_warehouses.filtered(
                lambda warehouse: not warehouse.direct_sales_approval_user_ids
            )
            if warehouses_without_approvers:
                raise UserError(
                    _(
                        "Assign at least one warehouse approver to: %s.",
                        ", ".join(warehouses_without_approvers.mapped("display_name")),
                    )
                )
            approvers = approval_warehouses.direct_sales_approval_user_ids
            old_state = record.state
            record.with_context(direct_sales_bypass_lock=True).write(
                {"state": "warehouse_pending"}
            )
            record.line_ids.with_context(direct_sales_warehouse_write=True).write(
                {
                    "approved_quantity": 0.0,
                    "warehouse_status": "pending",
                }
            )
            record._log_approval_event(
                "submitted",
                state_from=old_state,
                state_to="warehouse_pending",
            )
            record._schedule_activity_once(
                "anabtawi_direct_sales_invoice.mail_activity_direct_warehouse_approval",
                approvers,
                _("Approve direct invoice %s", record.name),
                _("Customer: %s", record.partner_id.display_name),
            )
            record._notify_users(
                approvers,
                _(
                    "Direct invoice <b>%(reference)s</b> was submitted for warehouse approval.",
                    reference=record.name,
                ),
            )
        return True

    def action_open_approval_wizard(self):
        self.ensure_one()
        self._check_warehouse_manager()
        self._check_user_warehouse_assignment()
        if self.state != "warehouse_pending":
            raise UserError(_("Only pending requests can be approved."))
        return {
            "name": _("Approve Warehouse Request"),
            "type": "ir.actions.act_window",
            "res_model": "direct.sales.warehouse.approval.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_direct_invoice_id": self.id},
        }

    def action_open_partial_approval_wizard(self):
        self.ensure_one()
        self._check_warehouse_manager()
        self._check_user_warehouse_assignment()
        if not self.company_id.allow_partial_warehouse_approval:
            raise UserError(_("Partial warehouse approval is disabled for this company."))
        if self.state != "warehouse_pending":
            raise UserError(_("Only pending requests can be partially approved."))
        return {
            "name": _("Partially Approve Warehouse Request"),
            "type": "ir.actions.act_window",
            "res_model": "direct.sales.partial.approval.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_direct_invoice_id": self.id},
        }

    def action_open_rejection_wizard(self):
        self.ensure_one()
        self._check_warehouse_manager()
        self._check_user_warehouse_assignment()
        if self.state != "warehouse_pending":
            raise UserError(_("Only pending requests can be rejected."))
        return {
            "name": _("Reject Warehouse Request"),
            "type": "ir.actions.act_window",
            "res_model": "direct.sales.rejection.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_direct_invoice_id": self.id},
        }

    def _approve_from_warehouse(self, partial=False, comment=None):
        self._check_warehouse_manager()
        self._check_user_warehouse_assignment()
        for record in self:
            if record.state != "warehouse_pending":
                raise UserError(_("Only pending warehouse requests can be approved."))
            if not partial:
                shortages = []
                for line in record.line_ids:
                    if (
                        record.company_id.allow_multi_warehouse_fulfillment
                        and line.allocation_ids
                    ):
                        unavailable_allocations = line.allocation_ids.filtered(
                            lambda allocation: float_compare(
                                allocation.available_quantity,
                                allocation.requested_quantity,
                                precision_rounding=line.product_uom_id.rounding,
                            )
                            < 0
                        )
                        shortages.extend(
                            _(
                                "%(product)s at %(warehouse)s",
                                product=line.product_id.display_name,
                                warehouse=allocation.warehouse_id.display_name,
                            )
                            for allocation in unavailable_allocations
                        )
                    elif (
                        float_compare(
                            line.free_quantity,
                            line.quantity,
                            precision_rounding=line.product_uom_id.rounding,
                        )
                        < 0
                    ):
                        shortages.append(line.product_id.display_name)
                if shortages:
                    raise UserError(
                        _(
                            "Insufficient free stock for: %s. Use Partial Approval or "
                            "replenish the selected warehouse.",
                            ", ".join(shortages),
                        )
                    )
                for line in record.line_ids:
                    line.with_context(direct_sales_warehouse_write=True).write(
                        {
                            "approved_quantity": line.quantity,
                            "warehouse_status": "approved",
                        }
                    )
            record._validate_approved_quantities(partial=partial)
            record._synchronize_allocation_approvals()
            record._validate_allocation_availability()
            has_partial = any(
                float_compare(
                    line.approved_quantity,
                    line.quantity,
                    precision_rounding=line.product_uom_id.rounding,
                )
                < 0
                for line in record.line_ids
            )
            target_state = "partially_approved" if has_partial else "warehouse_approved"
            old_state = record.state
            record.with_context(direct_sales_bypass_lock=True).write(
                {
                    "state": target_state,
                    "warehouse_approved_by": self.env.user.id,
                    "warehouse_approved_at": fields.Datetime.now(),
                    "warehouse_comment": comment or record.warehouse_comment,
                }
            )
            record._ensure_approval_pickings()
            record._complete_activities(
                "anabtawi_direct_sales_invoice.mail_activity_direct_warehouse_approval"
            )
            event = "partially_approved" if has_partial else "approved"
            record._log_approval_event(
                event,
                note=comment,
                state_from=old_state,
                state_to=target_state,
            )
            if (
                record.company_id.direct_sales_invoice_creation_policy
                == "on_warehouse_approval"
            ):
                record._create_customer_invoice(quantity_basis="approved")
            preparation_warehouses = record.warehouse_id
            if record.company_id.allow_multi_warehouse_fulfillment:
                preparation_warehouses |= record.allocation_ids.warehouse_id
            record._schedule_activity_once(
                "anabtawi_direct_sales_invoice.mail_activity_direct_stock_preparation",
                preparation_warehouses.direct_sales_user_ids
                | preparation_warehouses.direct_sales_approval_user_ids,
                _("Prepare goods for %s", record.name),
            )
            record._notify_users(
                record.user_id,
                _(
                    "Direct invoice <b>%(reference)s</b> was %(status)s by the warehouse.",
                    reference=record.name,
                    status=_("partially approved") if has_partial else _("approved"),
                ),
            )
        return True

    def _reject_from_warehouse(self, reason):
        self._check_warehouse_manager()
        self._check_user_warehouse_assignment()
        if not reason or not reason.strip():
            raise UserError(_("A rejection reason is required."))
        for record in self:
            if record.state != "warehouse_pending":
                raise UserError(_("Only pending warehouse requests can be rejected."))
            old_state = record.state
            record.line_ids.with_context(direct_sales_warehouse_write=True).write(
                {
                    "approved_quantity": 0.0,
                    "warehouse_status": "rejected",
                }
            )
            record.with_context(direct_sales_bypass_lock=True).write(
                {
                    "state": "rejected",
                    "rejection_reason": reason,
                    "warehouse_approved_by": self.env.user.id,
                    "warehouse_approved_at": fields.Datetime.now(),
                }
            )
            record._complete_activities(
                "anabtawi_direct_sales_invoice.mail_activity_direct_warehouse_approval"
            )
            record._log_approval_event(
                "rejected",
                note=reason,
                state_from=old_state,
                state_to="rejected",
            )
            record._notify_users(
                record.user_id,
                _(
                    "Direct invoice <b>%(reference)s</b> was rejected: %(reason)s",
                    reference=record.name,
                    reason=reason,
                ),
            )
        return True

    def _validate_approved_quantities(self, partial=False):
        for record in self:
            if not any(line.approved_quantity > 0 for line in record.line_ids):
                raise UserError(_("Approve a positive quantity on at least one line."))
            for line in record.line_ids:
                rounding = line.product_uom_id.rounding
                if float_compare(line.approved_quantity, 0.0, precision_rounding=rounding) < 0:
                    raise UserError(_("Approved quantities cannot be negative."))
                if (
                    float_compare(
                        line.approved_quantity,
                        line.quantity,
                        precision_rounding=rounding,
                    )
                    > 0
                ):
                    raise UserError(
                        _(
                            "Approved quantity cannot exceed requested quantity for %s.",
                            line.product_id.display_name,
                        )
                    )
                status = (
                    "rejected"
                    if float_is_zero(line.approved_quantity, precision_rounding=rounding)
                    else (
                        "partial"
                        if float_compare(
                            line.approved_quantity,
                            line.quantity,
                            precision_rounding=rounding,
                        )
                        < 0
                        else "approved"
                    )
                )
                line.with_context(direct_sales_warehouse_write=True).write(
                    {"warehouse_status": status}
                )
            if not partial and any(
                line.warehouse_status != "approved" for line in record.line_ids
            ):
                raise UserError(_("Use Partial Approval when any line is not fully approved."))

    def _validate_allocations(self):
        for record in self:
            if not record.company_id.allow_multi_warehouse_fulfillment:
                invalid = record.allocation_ids.filtered(
                    lambda allocation: allocation.warehouse_id != record.warehouse_id
                )
                if invalid:
                    raise UserError(
                        _("Multiple-warehouse fulfillment is disabled for this company.")
                    )
            unauthorized = record.allocation_ids.filtered(
                lambda allocation: allocation.warehouse_id
                not in record._get_permitted_warehouses()
            )
            if unauthorized:
                raise AccessError(
                    _(
                        "You are not permitted to allocate stock from: %s.",
                        ", ".join(unauthorized.mapped("warehouse_id.display_name")),
                    )
                )
            for line in record.line_ids.filtered("allocation_ids"):
                allocated = sum(line.allocation_ids.mapped("requested_quantity"))
                if float_compare(
                    allocated,
                    line.quantity,
                    precision_rounding=line.product_uom_id.rounding,
                ) != 0:
                    raise UserError(
                        _(
                            "Warehouse allocations for %(product)s must total the requested "
                            "quantity (%(quantity)s).",
                            product=line.product_id.display_name,
                            quantity=line.quantity,
                        )
                    )

    def _synchronize_allocation_approvals(self):
        for record in self:
            for line in record.line_ids.filtered("allocation_ids"):
                allocations = line.allocation_ids.sorted("id")
                current_total = sum(allocations.mapped("approved_quantity"))
                rounding = line.product_uom_id.rounding
                if float_is_zero(current_total, precision_rounding=rounding):
                    remaining = line.approved_quantity
                    for allocation in allocations:
                        approved = min(remaining, allocation.requested_quantity)
                        allocation.with_context(
                            direct_sales_warehouse_write=True
                        ).write(
                            {
                                "approved_quantity": approved,
                                "state": (
                                    "approved"
                                    if float_compare(
                                        approved,
                                        allocation.requested_quantity,
                                        precision_rounding=rounding,
                                    )
                                    == 0
                                    else (
                                        "partial"
                                        if approved > 0
                                        else "rejected"
                                    )
                                ),
                            }
                        )
                        remaining -= approved
                elif float_compare(
                    current_total,
                    line.approved_quantity,
                    precision_rounding=rounding,
                ) != 0:
                    raise UserError(
                        _(
                            "Approved allocations for %s must equal the line's approved quantity.",
                            line.product_id.display_name,
                        )
                    )

    def _validate_allocation_availability(self):
        for record in self:
            for allocation in record.allocation_ids.filtered(
                lambda item: item.approved_quantity > 0
            ):
                if (
                    float_compare(
                        allocation.approved_quantity,
                        allocation.available_quantity,
                        precision_rounding=allocation.product_uom_id.rounding,
                    )
                    > 0
                ):
                    raise UserError(
                        _(
                            "%(warehouse)s has insufficient free stock for %(product)s "
                            "(approved %(approved)s, free %(free)s).",
                            warehouse=allocation.warehouse_id.display_name,
                            product=allocation.product_id.display_name,
                            approved=allocation.approved_quantity,
                            free=allocation.available_quantity,
                        )
                    )

    def _approved_sources(self):
        """Yield dictionaries used to group standard stock moves by warehouse and source."""
        self.ensure_one()
        for line in self.line_ids:
            if line.approved_quantity <= 0:
                continue
            if (
                self.company_id.allow_multi_warehouse_fulfillment
                and line.allocation_ids
            ):
                for allocation in line.allocation_ids.filtered(
                    lambda item: item.approved_quantity > 0
                ):
                    yield {
                        "line": line,
                        "allocation": allocation,
                        "warehouse": allocation.warehouse_id,
                        "source": allocation.source_location_id,
                        "quantity": allocation.approved_quantity,
                    }
            else:
                yield {
                    "line": line,
                    "allocation": self.env["direct.sales.invoice.allocation"],
                    "warehouse": self.warehouse_id,
                    "source": self.source_location_id,
                    "quantity": line.approved_quantity,
                }

    def _ensure_approval_pickings(self):
        for record in self:
            stage = (
                "release"
                if record.stock_flow == "direct_delivery"
                else "preparation"
            )
            record._create_pickings_from_sources(stage, list(record._approved_sources()))
        return True

    def _create_pickings_from_sources(self, stage, sources):
        self.ensure_one()
        grouped = defaultdict(list)
        for source in sources:
            grouped[
                (
                    source["warehouse"].id,
                    source["source"].id,
                )
            ].append(source)
        customer_location = self.partner_id.property_stock_customer
        created = self.env["stock.picking"]
        for (warehouse_id, source_location_id), entries in grouped.items():
            warehouse = self.env["stock.warehouse"].browse(warehouse_id)
            source_location = self.env["stock.location"].browse(source_location_id)
            if stage == "preparation":
                destination = warehouse.direct_sales_dispatch_location_id
                picking_type = warehouse.direct_sales_operation_type_id
                if not destination or not picking_type:
                    raise UserError(
                        _(
                            "Complete direct sales dispatch configuration for warehouse %s.",
                            warehouse.display_name,
                        )
                    )
            else:
                destination = customer_location
                picking_type = warehouse.out_type_id
            existing = self.picking_ids.filtered(
                lambda picking: picking.direct_sales_stage == stage
                and picking.direct_sales_warehouse_id == warehouse
                and picking.location_id == source_location
                and picking.state != "cancel"
            )
            if existing:
                created |= existing
                continue
            picking = self.env["stock.picking"].create(
                {
                    "picking_type_id": picking_type.id,
                    "partner_id": self.partner_id.id,
                    "location_id": source_location.id,
                    "location_dest_id": destination.id,
                    "origin": self.name,
                    "company_id": self.company_id.id,
                    "direct_invoice_id": self.id,
                    "direct_sales_warehouse_id": warehouse.id,
                    "direct_sales_stage": stage,
                    "customer_invoice_id": self.invoice_id.id,
                }
            )
            moves = []
            for entry in entries:
                line = entry["line"]
                allocation = entry["allocation"]
                moves.append(
                    {
                        "name": line.name or line.product_id.display_name,
                        "product_id": line.product_id.id,
                        "product_uom_qty": entry["quantity"],
                        "product_uom": line.product_uom_id.id,
                        "location_id": source_location.id,
                        "location_dest_id": destination.id,
                        "picking_id": picking.id,
                        "company_id": self.company_id.id,
                        "origin": self.name,
                        "warehouse_id": warehouse.id,
                        "direct_invoice_line_id": line.id,
                        "direct_sales_allocation_id": allocation.id,
                    }
                )
            move_records = self.env["stock.move"].create(moves)
            if stage == "preparation":
                for move in move_records.filtered("direct_sales_allocation_id"):
                    move.direct_sales_allocation_id.with_context(
                        direct_sales_warehouse_write=True
                    ).write(
                        {
                            "picking_id": picking.id,
                            "stock_move_id": move.id,
                        }
                    )
            picking.action_confirm()
            picking.action_assign()
            created |= picking
        return created

    def action_prepare_goods(self):
        self._check_warehouse_user()
        self._check_user_warehouse_assignment()
        for record in self:
            if record.state not in ("warehouse_approved", "partially_approved"):
                raise UserError(
                    _("Only approved requests can be marked ready for pickup.")
                )
            if record.stock_flow == "dispatch_then_customer":
                preparations = record.picking_ids.filtered(
                    lambda picking: picking.direct_sales_stage == "preparation"
                    and picking.state != "cancel"
                )
                if not preparations or any(
                    picking.state != "done" for picking in preparations
                ):
                    raise UserError(
                        _(
                            "Validate every preparation transfer before marking the goods ready."
                        )
                    )
                sources = record._release_sources_from_preparation(preparations)
                record._create_pickings_from_sources("release", sources)
            else:
                releases = record.picking_ids.filtered(
                    lambda picking: picking.direct_sales_stage == "release"
                    and picking.state != "cancel"
                )
                if not releases:
                    record._ensure_approval_pickings()
                    releases = record.picking_ids.filtered(
                        lambda picking: picking.direct_sales_stage == "release"
                        and picking.state != "cancel"
                    )
                if any(
                    picking.state not in ("assigned", "partially_available")
                    for picking in releases
                ):
                    raise UserError(
                        _("The outgoing transfer must reserve stock before goods are ready.")
                    )
            old_state = record.state
            record.with_context(direct_sales_bypass_lock=True).write(
                {
                    "state": "ready",
                    "ready_date": fields.Datetime.now(),
                }
            )
            record._complete_activities(
                "anabtawi_direct_sales_invoice.mail_activity_direct_stock_preparation"
            )
            record._log_approval_event(
                "ready",
                state_from=old_state,
                state_to="ready",
            )
            record._notify_users(
                record.user_id,
                _(
                    "Goods for direct invoice <b>%s</b> are ready for pickup.",
                    record.name,
                ),
            )
        return True

    def _release_sources_from_preparation(self, preparations):
        self.ensure_one()
        quantities = defaultdict(float)
        metadata = {}
        for move in preparations.move_ids.filtered(lambda item: item.state == "done"):
            line = move.direct_invoice_line_id
            allocation = move.direct_sales_allocation_id
            quantity = move.product_uom._compute_quantity(
                move.quantity,
                line.product_uom_id,
                round=False,
            )
            key = (line.id, allocation.id, move.picking_id.direct_sales_warehouse_id.id)
            quantities[key] += quantity
            metadata[key] = (line, allocation, move.picking_id.direct_sales_warehouse_id)
        sources = []
        for key, quantity in quantities.items():
            line, allocation, warehouse = metadata[key]
            if quantity <= 0:
                continue
            approved_limit = (
                allocation.approved_quantity
                if allocation
                else line.approved_quantity
            )
            sources.append(
                {
                    "line": line,
                    "allocation": allocation,
                    "warehouse": warehouse,
                    "source": warehouse.direct_sales_dispatch_location_id,
                    "quantity": min(quantity, approved_limit),
                }
            )
        if not sources:
            raise UserError(_("No prepared quantities are available for customer release."))
        return sources

    def action_open_goods_release_wizard(self):
        self.ensure_one()
        self._check_warehouse_user()
        self._check_user_warehouse_assignment()
        if self.state != "ready":
            raise UserError(_("Only ready documents can release goods."))
        return {
            "name": _("Confirm Goods Release"),
            "type": "ir.actions.act_window",
            "res_model": "direct.sales.goods.release.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_direct_invoice_id": self.id},
        }

    def _check_cash_payment_before_release(self):
        self.ensure_one()
        if not self.payment_clearance_required:
            return True
        if not self.invoice_id:
            self._create_customer_invoice(quantity_basis="approved")
        if self.invoice_id.state == "draft":
            try:
                self.invoice_id.sudo().action_post()
            except Exception as error:
                raise UserError(
                    _(
                        "The cash-sale invoice must be posted before payment can be "
                        "registered: %s",
                        str(error),
                    )
                ) from error
        if self.invoice_id.payment_state != "paid":
            raise UserError(
                _(
                    "Payment is required before release. Register and reconcile full "
                    "payment on invoice %s, then retry.",
                    self.invoice_id.display_name,
                )
            )
        return True

    def _confirm_goods_release(self, receiver_name):
        self._check_warehouse_user()
        self._check_user_warehouse_assignment()
        self.ensure_one()
        if self.state != "ready":
            raise UserError(_("Only ready documents can release goods."))
        self._check_cash_payment_before_release()
        releases = self.picking_ids.filtered(
            lambda picking: picking.direct_sales_stage == "release"
            and picking.state != "cancel"
        )
        if not releases:
            raise UserError(_("No customer release transfer exists."))
        self.with_context(direct_sales_bypass_lock=True).write(
            {"customer_receiver_name": receiver_name}
        )
        for picking in releases.filtered(lambda item: item.state != "done"):
            result = picking.button_validate()
            if isinstance(result, dict):
                return result
        self._synchronize_goods_release()
        return self.action_view_invoice() if self.invoice_id else True

    def _sync_after_picking_done(self, picking):
        for record in self:
            if picking.direct_sales_stage == "release":
                releases = record.picking_ids.filtered(
                    lambda item: item.direct_sales_stage == "release"
                    and item.state != "cancel"
                )
                if releases and all(item.state == "done" for item in releases):
                    record._synchronize_goods_release()

    def _synchronize_goods_release(self):
        synchronized = False
        for record in self:
            releases = record.picking_ids.filtered(
                lambda picking: picking.direct_sales_stage == "release"
                and picking.state == "done"
            )
            if not releases:
                continue
            synchronized = True
            quantities = defaultdict(float)
            lots_by_line = defaultdict(lambda: self.env["stock.lot"])
            allocation_quantities = defaultdict(float)
            for move in releases.move_ids.filtered(lambda item: item.state == "done"):
                line = move.direct_invoice_line_id
                if not line:
                    continue
                quantity = move.product_uom._compute_quantity(
                    move.quantity,
                    line.product_uom_id,
                    round=False,
                )
                quantities[line.id] += quantity
                lots_by_line[line.id] |= move.move_line_ids.mapped("lot_id")
                if move.direct_sales_allocation_id:
                    allocation_quantities[move.direct_sales_allocation_id.id] += quantity
            for line in record.line_ids:
                quantity = quantities[line.id]
                if float_compare(
                    quantity,
                    line.approved_quantity,
                    precision_rounding=line.product_uom_id.rounding,
                ) > 0:
                    raise ValidationError(
                        _(
                            "Released quantity cannot exceed approved quantity for %s.",
                            line.product_id.display_name,
                        )
                    )
                line.with_context(direct_sales_warehouse_write=True).write(
                    {
                        "released_quantity": quantity,
                        "lot_ids": [Command.set(lots_by_line[line.id].ids)],
                        "warehouse_status": "released" if quantity > 0 else line.warehouse_status,
                    }
                )
            for allocation_id, quantity in allocation_quantities.items():
                allocation = self.env["direct.sales.invoice.allocation"].browse(
                    allocation_id
                )
                allocation.with_context(direct_sales_warehouse_write=True).write(
                    {
                        "released_quantity": quantity,
                        "state": "released",
                    }
                )
            if record.state not in ("released", "completed"):
                old_state = record.state
                record.with_context(direct_sales_bypass_lock=True).write(
                    {
                        "state": "released",
                        "released_by": self.env.user.id,
                        "released_at": fields.Datetime.now(),
                    }
                )
                record._log_approval_event(
                    "released",
                    state_from=old_state,
                    state_to="released",
                )
                record._notify_users(
                    record.user_id,
                    _(
                        "Goods for direct invoice <b>%s</b> were released.",
                        record.name,
                    ),
                )
            if (
                record.company_id.direct_sales_invoice_creation_policy
                == "on_goods_release"
            ):
                record._create_customer_invoice(quantity_basis="released")
            if (
                record.invoice_id
                and record.company_id.direct_sales_auto_post_invoice
                and record.invoice_id.state == "draft"
            ):
                try:
                    record.invoice_id.sudo().action_post()
                except Exception as error:
                    raise UserError(
                        _(
                            "Goods were released, but invoice %(invoice)s could not be "
                            "posted. Accounting configuration must be corrected: %(error)s",
                            invoice=record.invoice_id.display_name,
                            error=str(error),
                        )
                    ) from error
            record._update_completion_state()
        return synchronized

    def _prepare_invoice_values(self, quantity_basis):
        self.ensure_one()
        invoice_partner = self.partner_id.address_get(["invoice"]).get(
            "invoice", self.partner_id.id
        )
        invoice_lines = []
        for line in self.line_ids:
            quantity = (
                line.released_quantity
                if quantity_basis == "released"
                else line.approved_quantity
            )
            if float_is_zero(
                quantity, precision_rounding=line.product_uom_id.rounding
            ):
                continue
            invoice_lines.append(
                Command.create(
                    {
                        "product_id": line.product_id.id,
                        "name": line.name or line.product_id.display_name,
                        "quantity": quantity,
                        "product_uom_id": line.product_uom_id.id,
                        "price_unit": line.price_unit,
                        "discount": line.discount,
                        "tax_ids": [Command.set(line.tax_ids.ids)],
                        "analytic_distribution": line.analytic_distribution,
                        "direct_invoice_line_id": line.id,
                    }
                )
            )
        if not invoice_lines:
            raise UserError(_("There are no approved or released quantities to invoice."))
        values = {
            "move_type": "out_invoice",
            "partner_id": invoice_partner,
            "invoice_date": self.invoice_date,
            "invoice_payment_term_id": self.payment_term_id.id,
            "currency_id": self.currency_id.id,
            "fiscal_position_id": self.fiscal_position_id.id,
            "invoice_user_id": self.user_id.id,
            "team_id": self.team_id.id,
            "invoice_origin": self.name,
            "ref": self.name,
            "company_id": self.company_id.id,
            "direct_sales_invoice_id": self.id,
            "pricelist_id": self.pricelist_id.id,
            "pickup_warehouse_id": self.warehouse_id.id,
            "warehouse_approved_by": self.warehouse_approved_by.id,
            "warehouse_approved_at": self.warehouse_approved_at,
            "direct_sales_picking_ids": [Command.set(self.picking_ids.ids)],
            "invoice_line_ids": invoice_lines,
            "narration": self.customer_note,
        }
        if self.company_id.direct_sales_journal_id:
            values["journal_id"] = self.company_id.direct_sales_journal_id.id
        return values

    def _create_customer_invoice(self, quantity_basis):
        self.ensure_one()
        if self.invoice_id and self.invoice_id.state != "cancel":
            return self.invoice_id
        existing = (
            self.env["account.move"]
            .sudo()
            .search(
                [
                    ("direct_sales_invoice_id", "=", self.id),
                    ("move_type", "=", "out_invoice"),
                    ("state", "!=", "cancel"),
                ],
                limit=1,
            )
        )
        if existing:
            self.with_context(direct_sales_bypass_lock=True).write(
                {"invoice_id": existing.id}
            )
            return existing
        try:
            with self.env.cr.savepoint():
                invoice = (
                    self.env["account.move"]
                    .sudo()
                    .with_company(self.company_id)
                    .create(self._prepare_invoice_values(quantity_basis))
                )
                self.with_context(direct_sales_bypass_lock=True).write(
                    {"invoice_id": invoice.id}
                )
                self.picking_ids.sudo().with_context(
                    direct_sales_link_write=True
                ).write({"customer_invoice_id": invoice.id})
                self.message_post(
                    body=_(
                        "Customer invoice <a href='#' data-oe-model='account.move' "
                        "data-oe-id='%(id)s'>%(invoice)s</a> was created.",
                        id=invoice.id,
                        invoice=invoice.display_name,
                    )
                )
                self._log_approval_event(
                    "invoice_created",
                    note=invoice.display_name,
                )
                if not self.company_id.direct_sales_auto_post_invoice:
                    accounting_users = self.env.ref(
                        "anabtawi_direct_sales_invoice.group_direct_invoice_accounting_user"
                    ).user_ids.filtered(
                        lambda user: self.company_id in user.company_ids
                    )
                    self._schedule_activity_once(
                        "anabtawi_direct_sales_invoice.mail_activity_direct_accounting_review",
                        accounting_users,
                        _("Review direct invoice %s", invoice.display_name),
                    )
                if self.is_cash_sale:
                    self._schedule_payment_collection(
                        summary=_("Collect cash-sale payment")
                    )
                return invoice
        except (UserError, ValidationError):
            raise
        except Exception as error:
            raise UserError(
                _("Customer invoice creation failed: %s", str(error))
            ) from error

    def _update_completion_state(self):
        for record in self:
            if (
                record.state == "released"
                and record.invoice_id
                and record.invoice_id.state == "posted"
            ):
                old_state = record.state
                record.with_context(direct_sales_bypass_lock=True).write(
                    {"state": "completed"}
                )
                record._log_approval_event(
                    "completed",
                    state_from=old_state,
                    state_to="completed",
                )
        return True

    def action_create_invoice(self):
        self.ensure_one()
        if not (
            self._is_direct_administrator()
            or self.env.user.has_group(
                "anabtawi_direct_sales_invoice.group_direct_invoice_accounting_user"
            )
        ):
            raise AccessError(_("Only Direct Invoice Accounting users may create invoices."))
        if self.state not in (
            "warehouse_approved",
            "partially_approved",
            "ready",
            "released",
        ):
            raise UserError(_("This document is not ready for invoicing."))
        basis = "released" if self.released_quantity > 0 else "approved"
        invoice = self._create_customer_invoice(quantity_basis=basis)
        return self.action_view_invoice() if invoice else True

    def action_register_payment(self):
        self.ensure_one()
        if not self.invoice_id or self.invoice_id.state != "posted":
            raise UserError(_("Post the customer invoice before registering payment."))
        return {
            "name": _("Register Payment"),
            "type": "ir.actions.act_window",
            "res_model": "account.payment.register",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "account.move",
                "active_ids": self.invoice_id.ids,
            },
        }

    def action_reset_to_draft(self):
        if not self._can_manage_commercial_terms():
            raise AccessError(
                _("Only a Direct Invoice Sales Manager may reset documents to Draft.")
            )
        for record in self:
            if record.state not in ("rejected", "cancelled"):
                raise UserError(_("Only rejected or cancelled documents can be reset."))
            if record.picking_ids.filtered(lambda picking: picking.state == "done"):
                raise UserError(_("A document with completed stock moves cannot be reset."))
            if record.invoice_id and record.invoice_id.state == "posted":
                raise UserError(_("A document with a posted invoice cannot be reset."))
            record.picking_ids.filtered(
                lambda picking: picking.state not in ("done", "cancel")
            ).action_cancel()
            record.with_context(direct_sales_bypass_lock=True).write(
                {
                    "state": "draft",
                    "warehouse_approved_by": False,
                    "warehouse_approved_at": False,
                    "released_by": False,
                    "released_at": False,
                    "ready_date": False,
                    "rejection_reason": False,
                    "warehouse_comment": False,
                    "customer_receiver_name": False,
                    "invoice_id": False,
                }
            )
            record.line_ids.with_context(direct_sales_warehouse_write=True).write(
                {
                    "approved_quantity": 0.0,
                    "released_quantity": 0.0,
                    "warehouse_status": "pending",
                    "lot_ids": [Command.clear()],
                }
            )
            record._log_approval_event("reset_to_draft")
        return True

    def action_cancel(self):
        for record in self:
            if record.state == "cancelled":
                continue
            if record.picking_ids.filtered(lambda picking: picking.state == "done"):
                raise UserError(
                    _(
                        "Goods have already moved. Use a standard return picking before "
                        "cancelling this document."
                    )
                )
            if record.invoice_id and record.invoice_id.state == "posted":
                raise UserError(
                    _("Create a standard credit note before cancelling a posted invoice.")
                )
            if record.state not in ("draft", "warehouse_pending") and not (
                record._is_direct_administrator()
                or self.env.user.has_group(
                    "anabtawi_direct_sales_invoice.group_direct_invoice_sales_manager"
                )
                or self.env.user.has_group(
                    "anabtawi_direct_sales_invoice.group_direct_invoice_warehouse_manager"
                )
            ):
                raise AccessError(
                    _("A manager is required to cancel an approved document.")
                )
            record.picking_ids.filtered(
                lambda picking: picking.state not in ("done", "cancel")
            ).action_cancel()
            old_state = record.state
            record.with_context(direct_sales_bypass_lock=True).write(
                {"state": "cancelled"}
            )
            record._log_approval_event(
                "cancelled",
                state_from=old_state,
                state_to="cancelled",
            )
        return True

    def action_create_return(self):
        self.ensure_one()
        picking = self.picking_ids.filtered(
            lambda item: item.direct_sales_stage == "release" and item.state == "done"
        )[:1]
        if not picking:
            raise UserError(_("No completed customer release transfer can be returned."))
        return {
            "name": _("Return Products"),
            "type": "ir.actions.act_window",
            "res_model": "stock.return.picking",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "stock.picking",
                "active_id": picking.id,
                "active_ids": picking.ids,
                "default_picking_id": picking.id,
            },
        }

    def action_create_credit_note(self):
        self.ensure_one()
        if not self.invoice_id or self.invoice_id.state != "posted":
            raise UserError(_("A posted customer invoice is required for a credit note."))
        return {
            "name": _("Credit Note"),
            "type": "ir.actions.act_window",
            "res_model": "account.move.reversal",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "account.move",
                "active_ids": self.invoice_id.ids,
                "default_journal_id": self.invoice_id.journal_id.id,
            },
        }

    def action_approve_price_overrides(self):
        if not self._can_manage_commercial_terms():
            raise AccessError(
                _("Only a Direct Invoice Sales Manager may approve price overrides.")
            )
        for record in self:
            if record.state != "draft":
                raise UserError(_("Price overrides can only be approved in Draft."))
            lines = record.line_ids.filtered("price_overridden")
            if not lines:
                raise UserError(_("There are no manual price overrides to approve."))
            missing_reason = lines.filtered(lambda line: not line.price_override_reason)
            if missing_reason:
                raise UserError(_("Every overridden price requires a reason."))
            lines.with_context(direct_sales_price_approval=True).write(
                {
                    "price_override_state": "approved",
                    "price_override_approved_by": self.env.user.id,
                }
            )
            record._log_approval_event("price_override_approved")
            record.message_post(
                body=_(
                    "Manual price overrides were approved by %s.",
                    self.env.user.display_name,
                )
            )
        return True

    def action_view_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_("No customer invoice has been created."))
        return {
            "name": _("Customer Invoice"),
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.invoice_id.id,
        }

    def action_view_pickings(self):
        self.ensure_one()
        action = {
            "name": _("Stock Pickings"),
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "view_mode": "list,form",
            "domain": [("id", "in", self.picking_ids.ids)],
            "context": {"create": False},
        }
        if len(self.picking_ids) == 1:
            action.update({"view_mode": "form", "res_id": self.picking_ids.id})
        return action

    def action_view_stock_moves(self):
        self.ensure_one()
        return {
            "name": _("Stock Moves"),
            "type": "ir.actions.act_window",
            "res_model": "stock.move",
            "view_mode": "list,form",
            "domain": [("id", "in", self.picking_ids.move_ids.ids)],
            "context": {"create": False},
        }

    def action_view_payments(self):
        self.ensure_one()
        payments = (
            self.invoice_id._get_reconciled_payments()
            if self.invoice_id
            else self.env["account.payment"]
        )
        action = {
            "name": _("Payments"),
            "type": "ir.actions.act_window",
            "res_model": "account.payment",
            "view_mode": "list,form",
            "domain": [("id", "in", payments.ids)],
            "context": {"create": False},
        }
        if len(payments) == 1:
            action.update({"view_mode": "form", "res_id": payments.id})
        return action

    def action_view_approvals(self):
        self.ensure_one()
        return {
            "name": _("Approval Audit"),
            "type": "ir.actions.act_window",
            "res_model": "direct.sales.invoice.approval",
            "view_mode": "list,form",
            "domain": [("direct_invoice_id", "=", self.id)],
            "context": {"create": False, "edit": False, "delete": False},
        }

    def action_view_attachments(self):
        self.ensure_one()
        return {
            "name": _("Attachments"),
            "type": "ir.actions.act_window",
            "res_model": "ir.attachment",
            "view_mode": "kanban,list,form",
            "domain": [
                ("res_model", "=", self._name),
                ("res_id", "=", self.id),
            ],
            "context": {
                "default_res_model": self._name,
                "default_res_id": self.id,
            },
        }


class DirectSalesInvoiceApproval(models.Model):
    _name = "direct.sales.invoice.approval"
    _description = "Direct Sales Approval Audit"
    _order = "event_date desc, id desc"
    _check_company_auto = True

    direct_invoice_id = fields.Many2one(
        "direct.sales.invoice",
        required=True,
        ondelete="cascade",
        index=True,
        check_company=True,
    )
    company_id = fields.Many2one(
        related="direct_invoice_id.company_id",
        store=True,
        index=True,
    )
    event = fields.Selection(
        [
            ("submitted", "Submitted"),
            ("approved", "Approved"),
            ("partially_approved", "Partially Approved"),
            ("rejected", "Rejected"),
            ("ready", "Ready for Pickup"),
            ("released", "Goods Released"),
            ("invoice_created", "Invoice Created"),
            ("completed", "Completed"),
            ("cancelled", "Cancelled"),
            ("reset_to_draft", "Reset to Draft"),
            ("price_override_approved", "Price Override Approved"),
        ],
        required=True,
        index=True,
    )
    user_id = fields.Many2one("res.users", required=True, readonly=True, index=True)
    event_date = fields.Datetime(required=True, readonly=True, index=True)
    state_from = fields.Selection(DIRECT_SALES_STATES, readonly=True)
    state_to = fields.Selection(DIRECT_SALES_STATES, readonly=True)
    note = fields.Text(readonly=True)
    quantity_snapshot = fields.Text(readonly=True)

    def write(self, vals):
        raise UserError(_("Approval audit entries are immutable."))

    def unlink(self):
        if not self.env.context.get("module_uninstall"):
            raise UserError(_("Approval audit entries cannot be deleted."))
        return super().unlink()
