# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # --- Computed flags ---
    discount_exception_required = fields.Boolean(
        string="Discount Above Allowed Ceiling",
        compute="_compute_discount_approval_requirements",
        store=True,
        readonly=True,
        help="True if any line discount exceeds the allowed ceiling (0/5/10) based on quantity tiers.",
    )

    discount_gt_5_required = fields.Boolean(
        string="Discount > 5% Present",
        compute="_compute_discount_approval_requirements",
        store=True,
        readonly=True,
        help="True if any line has Discount (%) > 5%. Triggers dual approval requirement.",
    )

    discount_approval_required = fields.Boolean(
        string="Discount Approval Required",
        compute="_compute_discount_approval_requirements",
        store=True,
        readonly=True,
        help="True if this order needs any discount approvals before confirmation.",
    )

    # --- Approvals ---
    commercial_approved = fields.Boolean(string="Commercial Approved", default=False, copy=False, tracking=True)
    commercial_approved_by = fields.Many2one("res.users", string="Commercial Approved By", copy=False, readonly=True)
    commercial_approved_date = fields.Datetime(string="Commercial Approved On", copy=False, readonly=True)

    accounting_approved = fields.Boolean(string="Accounting Approved", default=False, copy=False, tracking=True)
    accounting_approved_by = fields.Many2one("res.users", string="Accounting Approved By", copy=False, readonly=True)
    accounting_approved_date = fields.Datetime(string="Accounting Approved On", copy=False, readonly=True)

    exception_line_count = fields.Integer(
        string="Exception Lines",
        compute="_compute_discount_approval_requirements",
        store=True,
        readonly=True,
    )

    @api.depends(
        "order_line.discount_exceeds_limit",
        "order_line.discount_gt_5",
        "order_line.display_type",
        "state",
    )
    def _compute_discount_approval_requirements(self):
        for order in self:
            lines = order.order_line.filtered(lambda l: not l.display_type)
            exception_lines = lines.filtered("discount_exceeds_limit")

            order.exception_line_count = len(exception_lines)
            order.discount_exception_required = bool(exception_lines)
            order.discount_gt_5_required = any(lines.mapped("discount_gt_5"))

            # Approval required if:
            # - any line exceeds allowed ceiling OR
            # - any line discount > 5%
            order.discount_approval_required = bool(order.discount_exception_required or order.discount_gt_5_required)

            # If nothing requires approval anymore, clear approvals automatically
            if not order.discount_approval_required and (order.commercial_approved or order.accounting_approved):
                order._reset_discount_approvals(chatter_reason=None)

    # --- Reset approvals when order is modified after approval ---
    def _reset_discount_approvals(self, chatter_reason=None):
        for order in self:
            if not (order.commercial_approved or order.accounting_approved):
                continue
            order.write({
                "commercial_approved": False,
                "commercial_approved_by": False,
                "commercial_approved_date": False,
                "accounting_approved": False,
                "accounting_approved_by": False,
                "accounting_approved_date": False,
            })
            if chatter_reason:
                order.message_post(body=_(chatter_reason))

    def _on_discount_relevant_change(self, chatter_reason=None):
        # If approvals were granted, a relevant change invalidates them.
        for order in self:
            if order.commercial_approved or order.accounting_approved:
                order._reset_discount_approvals(chatter_reason=chatter_reason)

    # --- Approval actions (role-based) ---
    def action_approve_discount_commercial(self):
        self.ensure_one()
        if not self.env.user.has_group("sale_discount_exception_approval.group_discount_approver_commercial"):
            raise AccessError(_("Only Head of Commercial can approve discounts."))
        if not self.discount_approval_required:
            raise UserError(_("No discount approval is currently required."))
        self.write({
            "commercial_approved": True,
            "commercial_approved_by": self.env.user.id,
            "commercial_approved_date": fields.Datetime.now(),
        })
        self.message_post(body=_("Commercial approval granted by %s.", self.env.user.display_name))
        return True

    def action_approve_discount_accounting(self):
        self.ensure_one()
        if not self.env.user.has_group("sale_discount_exception_approval.group_discount_approver_accounting"):
            raise AccessError(_("Only Accounting can approve discounts."))
        if not self.discount_approval_required:
            raise UserError(_("No discount approval is currently required."))
        self.write({
            "accounting_approved": True,
            "accounting_approved_by": self.env.user.id,
            "accounting_approved_date": fields.Datetime.now(),
        })
        self.message_post(body=_("Accounting approval granted by %s.", self.env.user.display_name))
        return True

    # --- Server-side enforcement on confirm (all channels) ---
    def _check_discount_approvals_before_confirm(self):
        for order in self:
            if not order.discount_approval_required:
                continue

            # Rule: if any discount > 5%, BOTH must approve
            if order.discount_gt_5_required:
                if not (order.commercial_approved and order.accounting_approved):
                    raise UserError(_(
                        "This order has at least one line with Discount (%) > 5%%.\n"
                        "It requires BOTH Head of Commercial and Accounting approval before confirmation."
                    ))
            else:
                # Otherwise (only “above ceiling” but not >5), require Commercial only
                # Example: qty=50 discount=2% (ceiling is 0) => needs Commercial approval
                if not order.commercial_approved:
                    raise UserError(_(
                        "This order has discount exceptions (above the allowed ceiling for its quantity tier).\n"
                        "It requires Head of Commercial approval before confirmation."
                    ))

    def action_confirm(self):
        # Odoo docs highlight action_ methods like action_confirm as validation entrypoints
        self._check_discount_approvals_before_confirm()
        return super().action_confirm()

    # Copy safety (duplicate quotes/orders)
    def copy(self, default=None):
        default = dict(default or {})
        default.update({
            "commercial_approved": False,
            "commercial_approved_by": False,
            "commercial_approved_date": False,
            "accounting_approved": False,
            "accounting_approved_by": False,
            "accounting_approved_date": False,
        })
        new = super().copy(default)
        new.message_post(body=_("Order duplicated: discount approvals reset."))
        return new

    # Batch update safety (one2many commands)
    def write(self, vals):
        if "order_line" in vals:
            self._on_discount_relevant_change(chatter_reason="Order lines updated (batch). Discount approvals reset if needed.")
        return super().write(vals)
