from odoo import fields, models

from .pos_expense import OPEN_STATES


class PosConfig(models.Model):
    _inherit = "pos.config"

    expense_limit = fields.Float(
        string="Expense Limit",
        digits="Account",
        help="Maximum total of open POS expenses. Each expense reduces the available balance "
             "until it is approved, or, if refused, until the money is returned in the POS. "
             "Set to 0 to hide the Expense buttons.",
    )
    expense_pending_amount = fields.Float(
        string="Open Expenses (To Approve + Refused)",
        digits="Account",
        compute="_compute_expense_amounts",
    )
    expense_available_amount = fields.Float(
        string="Available Expense Balance",
        digits="Account",
        compute="_compute_expense_amounts",
    )

    def _compute_expense_amounts(self):
        pending_by_config = dict(
            self.env["pos.expense"].sudo()._read_group(
                [("config_id", "in", self.ids), ("state", "in", OPEN_STATES)],
                groupby=["config_id"],
                aggregates=["amount:sum"],
            )
        )
        for config in self:
            pending = pending_by_config.get(config._origin, 0.0)
            config.expense_pending_amount = pending
            config.expense_available_amount = config.expense_limit - pending

    def _get_unreturned_refused_expenses(self):
        self.ensure_one()
        return self.env["pos.expense"].sudo().search(
            [("config_id", "=", self.id), ("state", "=", "refused")],
            order="date, id",
        )
