from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ConstructionBudgetPoPaymentSchedule(models.Model):
    _name = "construction.budget.po.payment.schedule"
    _description = "Construction PO Payment Schedule"
    _order = "due_date asc, id asc"

    po_id = fields.Many2one("construction.budget.po", string="Purchase Order", required=True, ondelete="cascade")
    name = fields.Char(string="Milestone / Description", required=True)
    due_date = fields.Date(string="Due Date", default=fields.Date.context_today)
    amount_type = fields.Selection(
        [("percentage", "Percentage (%)"), ("fixed", "Fixed Amount")],
        string="Type",
        default="percentage",
        required=True,
    )
    percentage = fields.Float(string="Percentage (%)")
    amount = fields.Monetary(string="Amount", compute="_compute_amount", store=True, readonly=False)
    currency_id = fields.Many2one(related="po_id.currency_id", store=True, readonly=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("due", "Due"),
            ("invoiced", "Invoiced"),
            ("paid", "Paid"),
        ],
        string="Status",
        default="draft",
        tracking=True,
    )
    notes = fields.Text(string="Notes")

    @api.depends("percentage", "amount_type", "po_id.amount")
    def _compute_amount(self):
        for rec in self:
            if rec.amount_type == "percentage" and rec.po_id and rec.po_id.amount:
                rec.amount = (rec.po_id.amount * (rec.percentage or 0.0)) / 100.0
            elif not rec.amount:
                rec.amount = 0.0

    @api.onchange("amount", "po_id.amount")
    def _onchange_amount(self):
        if self.amount_type == "fixed" and self.po_id and self.po_id.amount:
            self.percentage = (self.amount / self.po_id.amount) * 100.0 if self.po_id.amount else 0.0
