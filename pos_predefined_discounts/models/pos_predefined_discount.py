# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class PosPredefinedDiscount(models.Model):
    _name = "pos.predefined.discount"
    _description = "POS Predefined Discount"
    _order = "sequence, id"
    _inherit = ["pos.load.mixin"]

    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    name = fields.Char(required=True)
    discount = fields.Float(string="Discount (%)", required=True, default=0.0)
    pos_config_id = fields.Many2one(
        "pos.config",
        required=True,
        ondelete="cascade",
        index=True,
    )

    @api.constrains("discount")
    def _check_discount_range(self):
        for rec in self:
            if rec.discount < 0.0 or rec.discount > 100.0:
                # keep it aligned with the POS behavior (0..100)
                raise ValidationError(_("Discount must be between 0 and 100."))

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [("pos_config_id", "=", config.id), ("active", "=", True)]

    @api.model
    def _load_pos_data_fields(self, config):
        return ["id", "name", "discount", "sequence", "pos_config_id"]


class PosConfig(models.Model):
    _inherit = "pos.config"

    predefined_discount_ids = fields.One2many(
        "pos.predefined.discount",
        "pos_config_id",
        string="Predefined Discounts",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_predefined_discount_ids = fields.One2many(
        related="pos_config_id.predefined_discount_ids",
        readonly=False,
    )

