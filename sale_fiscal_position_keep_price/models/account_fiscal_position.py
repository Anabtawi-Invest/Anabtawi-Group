from odoo import fields, models


class AccountFiscalPosition(models.Model):
    _inherit = "account.fiscal.position"

    keep_pricelist_price_after_tax_mapping = fields.Boolean(
        string="Keep Pricelist Price on Tax Mapping",
        help=(
            "When enabled, sales unit price keeps the original pricelist value and "
            "is not recalculated when taxes are remapped by this fiscal position."
        ),
    )
