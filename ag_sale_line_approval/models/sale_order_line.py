from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    approval_request_id = fields.Many2one(
        "approval.request",
        string="Approval Request",
        copy=False,
        readonly=True,
    )
    approval_request_status = fields.Selection(
        related="approval_request_id.request_status",
        string="Approval Request Status",
        store=True,
        readonly=True,
    )
    approval_state = fields.Selection(
        selection=[
            ("not_needed", "No Approval Needed"),
            ("to_request", "To Request"),
            ("new", "To Submit"),
            ("pending", "Submitted"),
            ("approved", "Approved"),
            ("refused", "Refused"),
            ("cancel", "Canceled"),
        ],
        string="Approval Status",
        compute="_compute_approval_state",
        store=True,
    )
    requested_discount = fields.Float(string="Requested Discount (%)", copy=False)
    requested_price_unit = fields.Float(string="Requested Unit Price", copy=False)
    has_requested_discount_change = fields.Boolean(copy=False)
    has_requested_price_change = fields.Boolean(copy=False)
    discount_ui = fields.Float(
        string="Discount (%)",
        compute="_compute_discount_ui",
        inverse="_inverse_discount_ui",
    )
    approval_required = fields.Boolean(
        string="Approval Required",
        compute="_compute_approval_state",
        store=True,
    )

    @api.depends(
        "approval_request_id",
        "approval_request_status",
        "has_requested_discount_change",
        "has_requested_price_change",
        "display_type",
    )
    def _compute_approval_state(self):
        for line in self:
            pending_changes = line.has_requested_discount_change or line.has_requested_price_change
            if line.display_type:
                line.approval_state = "not_needed"
                line.approval_required = False
            elif line.approval_request_id:
                line.approval_state = line.approval_request_status or "new"
                line.approval_required = pending_changes or line.approval_state in ("new", "pending", "refused", "cancel")
            elif pending_changes:
                line.approval_state = "to_request"
                line.approval_required = True
            else:
                line.approval_state = "not_needed"
                line.approval_required = False

    @api.depends(
        "discount",
        "requested_discount",
        "has_requested_discount_change",
        "approval_request_status",
    )
    def _compute_discount_ui(self):
        for line in self:
            if line.has_requested_discount_change and line.approval_request_status in ("new", "pending"):
                line.discount_ui = line.requested_discount
            else:
                line.discount_ui = line.discount

    def _inverse_discount_ui(self):
        for line in self:
            line.write({"discount": line.discount_ui})

    @api.model
    def _find_sale_approval_categories(self, company, change_type, discount_value=0.0):
        domain = [
            ("sale_line_approval_enabled", "=", True),
            ("sale_line_approval_type", "=", change_type),
            ("company_id", "=", company.id),
        ]
        order = "sequence, id"
        if change_type == "discount":
            domain += [
                ("sale_discount_min", "<=", discount_value),
                ("sale_discount_max", ">=", discount_value),
            ]
            order = "sale_discount_min desc, sequence, id"
        return self.env["approval.category"].search(domain, order=order)

    @api.model
    def _select_sale_approval_category(
        self,
        company,
        change_type,
        quantity,
        discount_value=0.0,
        quantity_rounding=0.01,
        raise_on_qty=False,
    ):
        categories = self._find_sale_approval_categories(company, change_type, discount_value)
        if not categories:
            return self.env["approval.category"]

        matching_categories = categories.filtered(
            lambda category: not category.sale_min_quantity
            or float_compare(quantity, category.sale_min_quantity, precision_rounding=quantity_rounding) >= 0
        )
        if matching_categories:
            return matching_categories[0]

        if raise_on_qty:
            required_qty = categories[0].sale_min_quantity
            raise UserError(
                _(
                    "You cannot request this %(change_type)s because the line quantity must be at least %(required_qty)s.",
                    change_type="discount" if change_type == "discount" else "price override",
                    required_qty=required_qty,
                )
            )

        return self.env["approval.category"]

    def _needs_discount_approval(self, target_discount):
        self.ensure_one()
        if self.display_type or self.order_id.state not in ("draft", "sent", "sale"):
            return False
        if float_compare(target_discount, self.discount, precision_digits=2) == 0:
            return False
        return bool(
            self._select_sale_approval_category(
                self.order_id.company_id,
                "discount",
                self.product_uom_qty,
                target_discount,
                quantity_rounding=self.product_uom_id.rounding,
                raise_on_qty=True,
            )
        )

    def _needs_price_approval(self, target_price):
        self.ensure_one()
        if self.display_type or self.order_id.state not in ("draft", "sent", "sale"):
            return False
        if float_compare(target_price, self.price_unit, precision_rounding=self.currency_id.rounding) == 0:
            return False
        return bool(
            self._select_sale_approval_category(
                self.order_id.company_id,
                "price_override",
                self.product_uom_qty,
                quantity_rounding=self.product_uom_id.rounding,
                raise_on_qty=True,
            )
        )

    def _get_sale_change_type(self):
        self.ensure_one()
        if self.has_requested_price_change and self.has_requested_discount_change:
            return "mixed"
        if self.has_requested_price_change:
            return "price_override"
        if self.has_requested_discount_change:
            return "discount"
        return False

    def _has_active_approval_lock(self):
        self.ensure_one()
        return bool(
            self.approval_request_id
            and self.approval_request_status in ("new", "pending")
            and (self.has_requested_discount_change or self.has_requested_price_change)
        )

    def _get_active_requested_category(self):
        self.ensure_one()
        if not self._has_active_approval_lock():
            return self.env["approval.category"]
        if self.has_requested_price_change:
            return self._find_sale_approval_categories(self.order_id.company_id, "price_override")[:1]
        if self.has_requested_discount_change:
            return self._find_sale_approval_categories(
                self.order_id.company_id,
                "discount",
                self.requested_discount,
            )[:1]
        return self.env["approval.category"]

    def _get_requested_category(self):
        self.ensure_one()
        if self.has_requested_price_change:
            return self._select_sale_approval_category(
                self.order_id.company_id,
                "price_override",
                self.product_uom_qty,
                quantity_rounding=self.product_uom_id.rounding,
                raise_on_qty=True,
            )
        if self.has_requested_discount_change:
            return self._select_sale_approval_category(
                self.order_id.company_id,
                "discount",
                self.product_uom_qty,
                self.requested_discount,
                quantity_rounding=self.product_uom_id.rounding,
                raise_on_qty=True,
            )
        return self.env["approval.category"]

    def _prepare_approval_request_vals(self, category):
        self.ensure_one()
        change_labels = []
        if self.has_requested_discount_change:
            change_labels.append(_("Discount: %(value)s%%", value=self.requested_discount))
        if self.has_requested_price_change:
            change_labels.append(_("Unit Price: %(value)s", value=self.requested_price_unit))

        return {
            "name": _("%(order)s - %(product)s", order=self.order_id.name or _("Quotation"), product=self.product_id.display_name),
            "category_id": category.id,
            "request_owner_id": self.env.user.id,
            "partner_id": self.order_id.partner_id.id,
            "reference": self.order_id.name,
            "amount": self.price_subtotal,
            "reason": "<p>%s</p>" % "<br/>".join(change_labels),
            "sale_order_line_id": self.id,
            "sale_line_change_type": self._get_sale_change_type(),
            "sale_line_requested_discount": self.requested_discount if self.has_requested_discount_change else 0.0,
            "sale_line_requested_price_unit": self.requested_price_unit if self.has_requested_price_change else 0.0,
        }

    def _open_approval_request_action(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Approval Request"),
            "res_model": "approval.request",
            "view_mode": "form",
            "res_id": self.approval_request_id.id,
            "target": "current",
        }

    def _ensure_approval_request(self, submit=True):
        self.ensure_one()
        if not (self.has_requested_discount_change or self.has_requested_price_change):
            raise UserError(_("There are no pending discount or price changes to send for approval."))

        category = self._get_requested_category()
        if not category:
            raise UserError(_("No approval category matches the requested sale line change."))

        request = self.approval_request_id
        if request and request.request_status == "new":
            request.sudo().write(self._prepare_approval_request_vals(category))
        else:
            if request and request.request_status == "pending":
                request.action_cancel()
            request = self.env["approval.request"].create(self._prepare_approval_request_vals(category))
            self.with_context(ag_skip_sale_line_approval=True).write({"approval_request_id": request.id})

        if submit and request.request_status == "new":
            request.action_confirm()
        return request

    def action_open_or_create_approval(self):
        self.ensure_one()
        if not self.approval_request_id:
            self._ensure_approval_request()
        return self._open_approval_request_action()

    @api.model_create_multi
    def create(self, vals_list):
        routed_payloads = []
        if self.env.context.get("ag_skip_sale_line_approval") or self.env.context.get("sale_write_from_compute"):
            return super().create(vals_list)

        for vals in vals_list:
            routed_payload = {}
            order = self.env["sale.order"].browse(vals["order_id"]) if vals.get("order_id") else self.env["sale.order"]
            company = order.company_id if order else self.env.company
            product_uom = self.env["uom.uom"].browse(vals["product_uom_id"]) if vals.get("product_uom_id") else self.env["uom.uom"]
            quantity_rounding = product_uom.rounding if product_uom else 0.01
            quantity = vals.get("product_uom_qty", 0.0)

            if vals.get("discount") and order and self._select_sale_approval_category(
                company,
                "discount",
                quantity,
                vals["discount"],
                quantity_rounding=quantity_rounding,
                raise_on_qty=True,
            ):
                routed_payload.update({
                    "requested_discount": vals["discount"],
                    "has_requested_discount_change": True,
                })
                vals["discount"] = 0.0

            if vals.get("price_unit") and order and self._select_sale_approval_category(
                company,
                "price_override",
                quantity,
                quantity_rounding=quantity_rounding,
                raise_on_qty=True,
            ):
                routed_payload.update({
                    "requested_price_unit": vals["price_unit"],
                    "has_requested_price_change": True,
                })
                vals.pop("price_unit", None)
                vals.pop("technical_price_unit", None)

            routed_payloads.append(routed_payload)

        lines = super().create(vals_list)
        for line, routed_payload in zip(lines, routed_payloads):
            if not routed_payload:
                continue
            line.with_context(ag_skip_sale_line_approval=True).write(routed_payload)
            line._ensure_approval_request()
        return lines

    def write(self, vals):
        if self.env.context.get("ag_skip_sale_line_approval") or self.env.context.get("sale_write_from_compute"):
            return super().write(vals)

        if any(key in vals for key in ("discount", "price_unit")):
            locked_lines = self.filtered(lambda line: line._has_active_approval_lock())
            if locked_lines:
                line_names = ", ".join(locked_lines.mapped("product_id.display_name"))
                raise UserError(
                    _(
                        "You cannot modify discount or unit price while approval is still pending for: %(lines)s",
                        lines=line_names,
                    )
                )

        if "product_uom_qty" in vals:
            for line in self.filtered(lambda record: record._has_active_approval_lock()):
                category = line._get_active_requested_category()
                if category and category.sale_min_quantity and float_compare(
                    vals["product_uom_qty"],
                    category.sale_min_quantity,
                    precision_rounding=line.product_uom_id.rounding,
                ) < 0:
                    raise UserError(
                        _(
                            "You cannot reduce the quantity below %(required_qty)s while approval is pending for %(product)s.",
                            required_qty=category.sale_min_quantity,
                            product=line.product_id.display_name,
                        )
                    )

        if "discount" not in vals and "price_unit" not in vals:
            return super().write(vals)

        regular_lines = self.env["sale.order.line"]
        routed_lines = self.env["sale.order.line"]
        for line in self:
            if line.display_type or line.order_id.state not in ("draft", "sent", "sale") or line.order_id.locked:
                regular_lines |= line
                continue
            if line.qty_invoiced > 0:
                regular_lines |= line
                continue
            if not line._needs_discount_approval(vals.get("discount", line.discount)) and not line._needs_price_approval(vals.get("price_unit", line.price_unit)):
                regular_lines |= line
                continue
            routed_lines |= line

        result = True
        if regular_lines:
            result = super(SaleOrderLine, regular_lines).write(vals)

        for line in routed_lines:
            direct_vals = dict(vals)
            approval_vals = {}

            if "discount" in vals and line._needs_discount_approval(vals["discount"]):
                approval_vals.update({
                    "requested_discount": vals["discount"],
                    "has_requested_discount_change": True,
                })
                direct_vals.pop("discount", None)

            if "price_unit" in vals and line._needs_price_approval(vals["price_unit"]):
                approval_vals.update({
                    "requested_price_unit": vals["price_unit"],
                    "has_requested_price_change": True,
                })
                direct_vals.pop("price_unit", None)
                direct_vals.pop("technical_price_unit", None)

            if direct_vals:
                result = super(SaleOrderLine, line).write(direct_vals) and result
            if approval_vals:
                super(SaleOrderLine, line.with_context(ag_skip_sale_line_approval=True)).write(approval_vals)
                line._ensure_approval_request()

        return result
