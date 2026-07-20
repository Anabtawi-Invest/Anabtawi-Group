# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class QcProductHold(models.Model):
    """Non-conforming product hold / quarantine (GMP control of
    nonconforming product). Suspect stock is placed on hold pending
    investigation, then released or disposed of by a Quality Manager."""
    _name = "qc.product.hold"
    _description = "Product Hold / Quarantine (GMP)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_held desc, id desc"

    name = fields.Char(
        string="Reference", required=True, copy=False, readonly=True,
        default=lambda self: _("New"), index=True,
    )
    branch_id = fields.Many2one(
        "qc.branch", string="Site", required=True, tracking=True, index=True,
    )
    date_held = fields.Datetime(
        string="Held On", required=True, default=fields.Datetime.now,
        tracking=True,
    )
    product_description = fields.Char(string="Product", required=True, tracking=True)
    lot_id = fields.Many2one("stock.lot", string="Lot / Serial")
    lot_ref = fields.Char(string="Lot Reference")
    qty_held = fields.Float(string="Quantity Held")
    uom_name = fields.Char(string="Unit")
    hold_type = fields.Selection(
        [
            ("quality_investigation", "Quality Investigation"),
            ("pending_test", "Pending Lab Test"),
            ("complaint", "Customer Complaint"),
            ("recall", "Recall Related"),
            ("supplier", "Blocked / Suspect Supplier"),
            ("other", "Other"),
        ],
        string="Hold Reason Type", default="quality_investigation",
        required=True, tracking=True,
    )
    reason = fields.Text(string="Reason for Hold", required=True)
    initiated_by_id = fields.Many2one(
        "res.users", string="Held By", tracking=True,
        default=lambda self: self.env.user,
    )
    recall_id = fields.Many2one(
        "qc.recall", string="Related Recall",
        help="Link to a recall/mock-recall record when this hold is part "
             "of a traceability exercise or real recall.",
    )
    status = fields.Selection(
        [
            ("on_hold", "On Hold"),
            ("released", "Released"),
            ("disposed", "Disposed"),
        ],
        string="Status", default="on_hold", required=True, tracking=True,
        index=True,
    )
    released_by_id = fields.Many2one(
        "res.users", string="Released/Disposed By", readonly=True,
    )
    release_date = fields.Datetime(string="Released/Disposed On", readonly=True)
    release_reason = fields.Text(string="Release / Disposition Justification")
    disposal_method = fields.Char(
        string="Disposal Method",
        help="e.g. Destroyed on site, returned to supplier, rework.",
    )
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True,
        default=lambda self: self.env.company,
    )
    note = fields.Text(string="Notes")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                seq = self.env["ir.sequence"].next_by_code("qc.product.hold")
                vals["name"] = seq or _("New")
        return super().create(vals_list)

    def _ensure_group(self, message):
        if not self.env.user.has_group(
                "site_quality_control.group_qc_quality_manager"):
            raise UserError(message)

    def action_release(self):
        self._ensure_group(_(
            "Only a Quality Manager can release held product."))
        for rec in self:
            if rec.status != "on_hold":
                raise UserError(_("Only held product can be released."))
            if not rec.release_reason:
                raise UserError(_(
                    "Enter a justification before releasing this hold."))
            rec.write({
                "status": "released",
                "released_by_id": self.env.user.id,
                "release_date": fields.Datetime.now(),
            })
        return True

    def action_dispose(self):
        self._ensure_group(_(
            "Only a Quality Manager can dispose of held product."))
        for rec in self:
            if rec.status != "on_hold":
                raise UserError(_("Only held product can be disposed of."))
            if not rec.release_reason or not rec.disposal_method:
                raise UserError(_(
                    "Enter the justification and disposal method before "
                    "confirming disposal."))
            rec.write({
                "status": "disposed",
                "released_by_id": self.env.user.id,
                "release_date": fields.Datetime.now(),
            })
        return True

    def action_reopen(self):
        self._ensure_group(_(
            "Only a Quality Manager can reopen a hold."))
        self.write({
            "status": "on_hold",
            "released_by_id": False,
            "release_date": False,
        })
        return True
