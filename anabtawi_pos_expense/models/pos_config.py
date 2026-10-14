from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    expense_limit = fields.Float(
        string="Expense Limit",
        digits="Account",
        help="Maximum total of POS expenses that can wait for approval at the same time. "
             "Each expense reduces the available balance until it is approved or refused. "
             "Set to 0 to hide the Expense button.",
    )
    expense_pending_amount = fields.Float(
        string="Expenses Waiting Approval",
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
                [("config_id", "in", self.ids), ("state", "=", "to_approve")],
                groupby=["config_id"],
                aggregates=["amount:sum"],
            )
        )
        for config in self:
            pending = pending_by_config.get(config._origin, 0.0)
            config.expense_pending_amount = pending
            config.expense_available_amount = config.expense_limit - pending
