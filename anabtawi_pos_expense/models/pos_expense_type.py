from odoo import fields, models


class PosExpenseType(models.Model):
    _name = "pos.expense.type"
    _description = "POS Expense Type"
    _order = "sequence, id"

    name = fields.Char(string="Expense Type", required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", string="Company")
    pos_config_ids = fields.Many2many(
        "pos.config",
        string="Point of Sale",
        help="Leave empty to make this expense type available in all Points of Sale.",
    )

    def _get_domain_for_config(self, config):
        return [
            ("company_id", "in", [False, config.company_id.id]),
            "|", ("pos_config_ids", "=", False), ("pos_config_ids", "in", config.id),
        ]
