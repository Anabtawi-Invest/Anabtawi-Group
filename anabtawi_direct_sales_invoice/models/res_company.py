from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    direct_sales_enabled = fields.Boolean(
        string="Enable Direct Sales Invoice",
        default=False,
    )
    direct_sales_invoice_creation_policy = fields.Selection(
        [
            ("on_warehouse_approval", "Create on Warehouse Approval"),
            ("on_goods_release", "Create on Goods Release"),
        ],
        string="Direct Invoice Creation Policy",
        default="on_goods_release",
        required=True,
    )
    direct_sales_auto_post_invoice = fields.Boolean(
        string="Automatically Post Direct Sales Invoice",
        default=False,
    )
    direct_sales_stock_flow = fields.Selection(
        [
            ("direct_delivery", "Direct Delivery"),
            ("dispatch_then_customer", "Dispatch then Customer"),
        ],
        string="Default Direct Sales Stock Flow",
        default="dispatch_then_customer",
        required=True,
    )
    cash_customer_release_policy = fields.Selection(
        [
            ("allow_before_payment", "Allow Release Before Payment"),
            ("require_payment", "Require Payment Before Goods Release"),
        ],
        string="Cash Customer Release Policy",
        default="allow_before_payment",
        required=True,
    )
    allow_multi_warehouse_fulfillment = fields.Boolean(
        string="Allow Multiple Warehouses per Direct Invoice",
        default=False,
    )
    allow_partial_warehouse_approval = fields.Boolean(
        string="Allow Partial Warehouse Approval",
        default=True,
    )
    direct_sales_journal_id = fields.Many2one(
        "account.journal",
        string="Default Direct Sales Journal",
        domain="[('type', '=', 'sale'), ('company_id', '=', id)]",
        check_company=True,
    )
    direct_sales_default_dispatch_location_id = fields.Many2one(
        "stock.location",
        string="Default Direct Sales Dispatch Location",
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [id, False])]",
        check_company=True,
        help=(
            "Reused when enabling a warehouse if the location belongs to that "
            "warehouse; otherwise a warehouse-local Sales Dispatch location is created."
        ),
    )
    direct_sales_default_payment_term_id = fields.Many2one(
        "account.payment.term",
        string="Default Direct Sales Payment Term",
        check_company=True,
    )
    direct_sales_show_prices_on_preparation = fields.Boolean(
        string="Show Prices on Warehouse Preparation Sheet",
        default=False,
    )
    direct_sales_price_override_approval = fields.Boolean(
        string="Enable Price Override Approval",
        default=True,
    )
