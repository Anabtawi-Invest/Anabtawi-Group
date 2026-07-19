# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class QcRecall(models.Model):
    """Product recall / mock-recall (traceability exercise) record.

    Standards require periodic mock recalls proving a lot can be traced and
    recovered within a target time. This model documents both real recalls
    and exercises: scope, lot, quantities, elapsed time and the result."""
    _name = "qc.recall"
    _description = "Product Recall / Traceability Exercise"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_started desc, id desc"

    name = fields.Char(
        string="Reference", required=True, copy=False, readonly=True,
        default=lambda self: _("New"), index=True,
    )
    recall_type = fields.Selection(
        [("mock", "Mock Recall (exercise)"), ("actual", "Actual Recall")],
        string="Type", default="mock", required=True, tracking=True,
    )
    product_description = fields.Char(
        string="Product", required=True, tracking=True,
    )
    lot_id = fields.Many2one(
        "stock.lot", string="Lot / Serial",
        help="Odoo lot being traced, when available.",
    )
    lot_ref = fields.Char(
        string="Lot Reference",
        help="Free-text lot/batch reference when no Odoo lot is used.",
    )
    reason = fields.Text(string="Reason / Scenario", tracking=True)
    date_started = fields.Datetime(
        string="Started", required=True, default=fields.Datetime.now,
        tracking=True,
    )
    date_completed = fields.Datetime(string="Completed", tracking=True)
    duration_hours = fields.Float(
        string="Duration (hours)", compute="_compute_duration", store=True,
    )
    initiated_by_id = fields.Many2one(
        "res.users", string="Initiated By",
        default=lambda self: self.env.user, tracking=True,
    )
    branch_ids = fields.Many2many(
        "qc.branch", string="Affected Sites",
    )
    qty_affected = fields.Float(string="Quantity Affected")
    qty_recovered = fields.Float(string="Quantity Recovered")
    recovery_rate = fields.Float(
        string="Recovery Rate (%)", compute="_compute_recovery", store=True,
    )
    receiving_ids = fields.One2many(
        "qc.receiving.inspection", compute="_compute_receiving_ids",
        string="Related Receiving Inspections",
    )
    result = fields.Selection(
        [("pass", "Passed"), ("fail", "Failed")],
        string="Result", tracking=True,
        help="A mock recall passes when the lot is fully traced and "
             "recovered within the target time (commonly 2-4 hours).",
    )
    state = fields.Selection(
        [("open", "In Progress"), ("closed", "Closed")],
        string="Status", default="open", required=True, tracking=True,
    )
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True,
        default=lambda self: self.env.company,
    )
    note = fields.Text(string="Findings / Lessons Learned")

    @api.depends("date_started", "date_completed")
    def _compute_duration(self):
        for recall in self:
            if recall.date_started and recall.date_completed:
                delta = recall.date_completed - recall.date_started
                recall.duration_hours = delta.total_seconds() / 3600.0
            else:
                recall.duration_hours = 0.0

    @api.depends("qty_affected", "qty_recovered")
    def _compute_recovery(self):
        for recall in self:
            recall.recovery_rate = (
                recall.qty_recovered / recall.qty_affected * 100.0
                if recall.qty_affected else 0.0)

    def _compute_receiving_ids(self):
        Receiving = self.env["qc.receiving.inspection"]
        for recall in self:
            domain = []
            if recall.lot_id:
                domain = [("lot_id", "=", recall.lot_id.id)]
            elif recall.lot_ref:
                domain = [("lot_ref", "=", recall.lot_ref)]
            recall.receiving_ids = Receiving.search(domain) if domain \
                else Receiving.browse()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                seq = self.env["ir.sequence"].next_by_code("qc.recall")
                vals["name"] = seq or _("New")
        return super().create(vals_list)

    def action_close(self):
        for recall in self:
            if recall.state != "open":
                raise UserError(_("This recall is already closed."))
            if not recall.result:
                raise UserError(_("Set the result before closing."))
            if not recall.date_completed:
                recall.date_completed = fields.Datetime.now()
        self.write({"state": "closed"})
        return True

    def action_reopen(self):
        if not self.env.user.has_group(
                "site_quality_control.group_qc_admin"):
            raise UserError(_(
                "Only a Quality Administrator can reopen a closed recall."))
        self.write({"state": "open"})
        return True
