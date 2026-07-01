from odoo import fields, models


class ProductPricelistItem(models.Model):
    _inherit = "product.pricelist.item"

    pricelist_is_provider = fields.Boolean(
        related="pricelist_id.is_provider",
        string="Is Provider Pricelist",
        readonly=True,
    )
    provider_commission = fields.Float(string="Provider Commission (%)", digits=(16, 2))
    talabat_contribution = fields.Float(string="Talabat Contribution (%)", digits=(16, 2))
    anabtawi_contribution = fields.Float(string="Anabtawi Contribution (%)", digits=(16, 2))
