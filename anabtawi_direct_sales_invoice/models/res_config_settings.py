from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    direct_sales_enabled = fields.Boolean(
        related="company_id.direct_sales_enabled", readonly=False
    )
    direct_sales_invoice_creation_policy = fields.Selection(
        related="company_id.direct_sales_invoice_creation_policy", readonly=False
    )
    direct_sales_auto_post_invoice = fields.Boolean(
        related="company_id.direct_sales_auto_post_invoice", readonly=False
    )
    direct_sales_stock_flow = fields.Selection(
        related="company_id.direct_sales_stock_flow", readonly=False
    )
    cash_customer_release_policy = fields.Selection(
        related="company_id.cash_customer_release_policy", readonly=False
    )
    allow_multi_warehouse_fulfillment = fields.Boolean(
        related="company_id.allow_multi_warehouse_fulfillment", readonly=False
    )
    allow_partial_warehouse_approval = fields.Boolean(
        related="company_id.allow_partial_warehouse_approval", readonly=False
    )
    direct_sales_journal_id = fields.Many2one(
        related="company_id.direct_sales_journal_id", readonly=False
    )
    direct_sales_default_dispatch_location_id = fields.Many2one(
        related="company_id.direct_sales_default_dispatch_location_id",
        readonly=False,
    )
    direct_sales_default_payment_term_id = fields.Many2one(
        related="company_id.direct_sales_default_payment_term_id", readonly=False
    )
    direct_sales_show_prices_on_preparation = fields.Boolean(
        related="company_id.direct_sales_show_prices_on_preparation", readonly=False
    )
    direct_sales_price_override_approval = fields.Boolean(
        related="company_id.direct_sales_price_override_approval", readonly=False
    )
    direct_sales_max_discount_percent = fields.Float(
        related="company_id.direct_sales_max_discount_percent", readonly=False
    )
