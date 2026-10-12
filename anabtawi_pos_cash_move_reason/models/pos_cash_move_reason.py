from odoo import api, fields, models
from odoo.fields import Domain


class PosCashMoveReason(models.Model):
    _name = "pos.cash.move.reason"
    _description = "POS Cash In/Out Reason"
    _inherit = ["pos.load.mixin"]
    _order = "sequence, id"

    name = fields.Char(string="Reason", required=True, translate=True)
    move_type = fields.Selection(
        [
            ("in", "Cash In"),
            ("out", "Cash Out"),
            ("both", "Both"),
        ],
        string="Type",
        required=True,
        default="both",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", string="Company")
    pos_config_ids = fields.Many2many(
        "pos.config",
        string="Point of Sale",
        help="Leave empty to show this reason in all Points of Sale.",
    )

    @api.model
    def _load_pos_data_domain(self, data, config):
        return Domain.AND([
            [("company_id", "in", [False, config.company_id.id])],
            ["|", ("pos_config_ids", "=", False), ("pos_config_ids", "in", config.id)],
        ])

    @api.model
    def _load_pos_data_fields(self, config):
        return ["id", "name", "move_type", "sequence"]
