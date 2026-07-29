from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare


class DirectSalesInvoiceAllocation(models.Model):
    _name = "direct.sales.invoice.allocation"
    _description = "Direct Sales Warehouse Allocation"
    _order = "direct_invoice_line_id, id"
    _check_company_auto = True

    direct_invoice_line_id = fields.Many2one(
        "direct.sales.invoice.line",
        required=True,
        ondelete="cascade",
        index=True,
        check_company=True,
    )
    direct_invoice_id = fields.Many2one(
        related="direct_invoice_line_id.direct_invoice_id", store=True, index=True
    )
    company_id = fields.Many2one(
        related="direct_invoice_id.company_id", store=True, index=True
    )
    currency_id = fields.Many2one(related="direct_invoice_id.currency_id")
    product_id = fields.Many2one(
        related="direct_invoice_line_id.product_id", store=True, index=True
    )
    product_uom_id = fields.Many2one(
        related="direct_invoice_line_id.product_uom_id"
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        required=True,
        check_company=True,
        domain="[('direct_sales_enabled', '=', True), ('company_id', '=', company_id)]",
        index=True,
    )
    source_location_id = fields.Many2one(
        "stock.location",
        required=True,
        check_company=True,
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [company_id, False])]",
    )
    requested_quantity = fields.Float(required=True, digits="Product Unit")
    approved_quantity = fields.Float(digits="Product Unit", copy=False)
    released_quantity = fields.Float(
        digits="Product Unit", readonly=True, copy=False
    )
    available_quantity = fields.Float(
        compute="_compute_available_quantity", digits="Product Unit"
    )
    picking_id = fields.Many2one(
        "stock.picking", readonly=True, copy=False, check_company=True
    )
    stock_move_id = fields.Many2one(
        "stock.move", readonly=True, copy=False, check_company=True
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("partial", "Partially Approved"),
            ("rejected", "Rejected"),
            ("released", "Released"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        copy=False,
        index=True,
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
                    "state": "draft",
                    "picking_id": False,
                    "stock_move_id": False,
                }
            )
            prepared_vals_list.append(prepared)
        return super().create(prepared_vals_list)

    @api.onchange("warehouse_id")
    def _onchange_warehouse_id(self):
        for allocation in self:
            allocation.source_location_id = allocation.warehouse_id.lot_stock_id

    @api.depends("product_id", "source_location_id", "company_id", "product_uom_id")
    def _compute_available_quantity(self):
        for allocation in self:
            if not (
                allocation.product_id
                and allocation.source_location_id
                and allocation.product_uom_id
            ):
                allocation.available_quantity = 0.0
                continue
            product = allocation.product_id.with_context(
                location=allocation.source_location_id.id,
                allowed_company_ids=[allocation.company_id.id],
            )
            allocation.available_quantity = product.uom_id._compute_quantity(
                product.free_qty, allocation.product_uom_id, round=False
            )

    def write(self, vals):
        if {
            "approved_quantity",
            "released_quantity",
            "state",
            "picking_id",
            "stock_move_id",
        }.intersection(vals) and not self.env.context.get(
            "direct_sales_warehouse_write"
        ):
            raise UserError(
                _("Allocation approval and stock links are controlled by warehouse actions.")
            )
        if {
            "warehouse_id",
            "source_location_id",
            "requested_quantity",
        }.intersection(vals) and not self.env.context.get(
            "direct_sales_warehouse_write"
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
                raise UserError(
                    _("Only Direct Invoice commercial users may change allocations.")
                )
            if self.filtered(lambda item: item.direct_invoice_id.state != "draft"):
                raise UserError(_("Allocations are frozen after warehouse submission."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda item: item.direct_invoice_id.state != "draft"):
            raise UserError(_("Allocations can only be deleted in Draft."))
        return super().unlink()

    @api.constrains("requested_quantity", "approved_quantity", "released_quantity")
    def _check_quantities(self):
        for allocation in self:
            rounding = allocation.product_uom_id.rounding
            if float_compare(
                allocation.requested_quantity, 0.0, precision_rounding=rounding
            ) <= 0:
                raise ValidationError(_("Allocated requested quantity must be positive."))
            if float_compare(
                allocation.approved_quantity,
                allocation.requested_quantity,
                precision_rounding=rounding,
            ) > 0:
                raise ValidationError(
                    _("Allocated approved quantity cannot exceed requested quantity.")
                )
            if float_compare(
                allocation.released_quantity,
                allocation.approved_quantity,
                precision_rounding=rounding,
            ) > 0:
                raise ValidationError(
                    _("Allocated released quantity cannot exceed approved quantity.")
                )

    @api.constrains("warehouse_id", "source_location_id")
    def _check_source_warehouse(self):
        for allocation in self:
            if (
                allocation.source_location_id
                and not allocation.warehouse_id._direct_sales_contains_location(
                    allocation.source_location_id
                )
            ):
                raise ValidationError(
                    _("Allocation source location must belong to its warehouse.")
                )
