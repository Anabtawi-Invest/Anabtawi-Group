from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    use_delivery_group = fields.Boolean(
        string="Split Delivery by Group",
        compute="_compute_use_delivery_group",
    )

    @api.depends("partner_id", "company_id", "company_id.delivery_split_location_ids")
    def _compute_use_delivery_group(self):
        for order in self:
            locations = order.company_id.delivery_split_location_ids
            customer_location = order.partner_id.with_company(order.company_id).property_stock_customer
            order.use_delivery_group = bool(customer_location and customer_location in locations)
