from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class PosDiscountProfile(models.Model):
    _name = "pos.discount.profile"
    _description = "POS Discount Profile"

    name = fields.Char(required=True)
    line_ids = fields.One2many("pos.discount.profile.line", "profile_id", string="Percent Buttons")

    allow_fixed_total_decimal = fields.Boolean(
        string="Allow Fixed Total Discount (Decimal < 1.0)",
        default=True,
    )
    max_fixed_total = fields.Float(
        string="Max Fixed Total Discount",
        default=0.99,
        help="Hard limit for fixed total discount (must be < 1.0). Recommended: 0.99",
    )

    @api.constrains("max_fixed_total")
    def _check_max_fixed_total(self):
        for rec in self:
            if rec.max_fixed_total >= 1.0:
                raise ValidationError(_("Max Fixed Total Discount must be < 1.0 (e.g. 0.99)."))
            if rec.max_fixed_total <= 0:
                raise ValidationError(_("Max Fixed Total Discount must be > 0."))


class PosDiscountProfileLine(models.Model):
    _name = "pos.discount.profile.line"
    _description = "POS Discount Button"

    profile_id = fields.Many2one("pos.discount.profile", required=True, ondelete="cascade")
    name = fields.Char(required=True, help="Button label, e.g. 10%")
    percent = fields.Float(required=True)

    @api.constrains("percent")
    def _check_percent(self):
        for rec in self:
            if rec.percent <= 0 or rec.percent > 100:
                raise ValidationError(_("Percent must be between 0 and 100."))
