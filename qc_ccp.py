# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    """Surfaces the QC Approved Supplier status on purchase orders.

    Blocked suppliers (per the Approved Supplier list, ISO 22000 §7.1.6)
    cannot be confirmed without a documented Quality Manager override.
    Conditional suppliers only raise a warning; purchasing may proceed."""
    _inherit = "purchase.order"

    qc_supplier_status = fields.Selection(
        [
            ("approved", "Approved"),
            ("conditional", "Conditional"),
            ("blocked", "Blocked"),
        ],
        string="QC Supplier Status", compute="_compute_qc_supplier_status",
        help="Status of this supplier on the Quality Control Approved "
             "Supplier list. Empty when the supplier is not listed.",
    )
    qc_block_overridden = fields.Boolean(
        string="QC Block Overridden", copy=False,
        help="A Quality Manager has authorised this purchase order despite "
             "the supplier being blocked.",
    )
    qc_override_reason = fields.Text(
        string="Override Justification", copy=False,
        help="Mandatory justification recorded when overriding a blocked "
             "supplier. Posted permanently to the chatter log.",
    )
    qc_override_by_id = fields.Many2one(
        "res.users", string="Override Granted By", copy=False, readonly=True,
    )
    qc_override_date = fields.Datetime(
        string="Override Date", copy=False, readonly=True,
    )

    @api.depends("partner_id", "company_id")
    def _compute_qc_supplier_status(self):
        Supplier = self.env["qc.approved.supplier"]
        for order in self:
            order.qc_supplier_status = (
                Supplier._status_for_partner(order.partner_id, order.company_id)
                if order.partner_id else False)

    @api.onchange("partner_id")
    def _onchange_partner_id_qc_supplier_status(self):
        for order in self:
            order.qc_block_overridden = False
            order.qc_override_reason = False
            order.qc_override_by_id = False
            order.qc_override_date = False
        if not self.partner_id:
            return
        status = self.env["qc.approved.supplier"]._status_for_partner(
            self.partner_id, self.company_id)
        if status == "blocked":
            return {"warning": {
                "title": _("Supplier Blocked by Quality Control"),
                "message": _(
                    "%(supplier)s is BLOCKED on the Approved Supplier list. "
                    "This purchase order cannot be confirmed unless a "
                    "Quality Manager grants a documented override.")
                    % {"supplier": self.partner_id.display_name},
            }}
        if status == "conditional":
            return {"warning": {
                "title": _("Conditional Supplier"),
                "message": _(
                    "%(supplier)s is CONDITIONALLY approved by Quality "
                    "Control. Check the approved scope and any certificate "
                    "expiry before ordering.")
                    % {"supplier": self.partner_id.display_name},
            }}

    def write(self, vals):
        if "partner_id" in vals:
            vals.setdefault("qc_block_overridden", False)
            vals.setdefault("qc_override_reason", False)
            vals.setdefault("qc_override_by_id", False)
            vals.setdefault("qc_override_date", False)
        return super().write(vals)

    # ------------------------------------------------------------------
    # Override workflow
    # ------------------------------------------------------------------
    def action_qc_override_block(self):
        if not self.env.user.has_group(
                "site_quality_control.group_qc_quality_manager"):
            raise UserError(_(
                "Only a Quality Manager can override a blocked supplier."))
        for order in self:
            if order.qc_supplier_status != "blocked":
                raise UserError(_(
                    "This supplier is not currently blocked."))
            if not order.qc_override_reason:
                raise UserError(_(
                    "Enter a justification before overriding the block."))
            order.write({
                "qc_block_overridden": True,
                "qc_override_by_id": self.env.user.id,
                "qc_override_date": fields.Datetime.now(),
            })
            order.message_post(body=_(
                "Blocked-supplier purchase override granted by %(user)s "
                "for supplier %(supplier)s. Reason: %(reason)s") % {
                "user": self.env.user.name,
                "supplier": order.partner_id.display_name,
                "reason": order.qc_override_reason,
            })
        return True

    # ------------------------------------------------------------------
    # Confirmation gate
    # ------------------------------------------------------------------
    def button_confirm(self):
        for order in self:
            if not order.partner_id:
                continue
            status = self.env["qc.approved.supplier"]._status_for_partner(
                order.partner_id, order.company_id)
            if status == "blocked" and not order.qc_block_overridden:
                raise UserError(_(
                    "Supplier %(supplier)s is BLOCKED on the Quality "
                    "Control Approved Supplier list. This purchase order "
                    "cannot be confirmed until a Quality Manager grants an "
                    "override with a documented justification.")
                    % {"supplier": order.partner_id.display_name})
        return super().button_confirm()
