from odoo import fields, models, tools


class ReportPosProviderPricelist(models.Model):
    _name = "report.pos.provider.pricelist"
    _description = "POS Provider Pricelist Report"
    _auto = False
    _order = "date_order desc, order_id desc"
    _rec_name = "order_id"

    date_order = fields.Datetime(string="Order Date", readonly=True)
    order_id = fields.Many2one("pos.order", string="Order ID", readonly=True)
    talabat_id = fields.Char(string="Talabat ID", readonly=True)
    pricelist_id = fields.Many2one("product.pricelist", string="Pricelist", readonly=True)
    product_id = fields.Many2one("product.product", string="Product", readonly=True)
    tax_names = fields.Char(string="Taxes", readonly=True)
    qty = fields.Float(string="Quantity", readonly=True)
    product_uom_id = fields.Many2one("uom.uom", string="Unit of Measure", readonly=True)
    applied_discount = fields.Float(string="Applied Discount (%)", readonly=True)
    unit_price = fields.Float(string="Unit Price", readonly=True)
    total_excluded = fields.Monetary(string="Total Tax Excluded", readonly=True)
    total_included = fields.Monetary(string="Total Tax Included", readonly=True)
    discount_amount = fields.Monetary(string="Discount Amount", readonly=True)
    provider_commission = fields.Float(string="Provider Commission (%)", readonly=True)
    talabat_contribution = fields.Float(string="Talabat Contribution (%)", readonly=True)
    anabtawi_contribution = fields.Float(string="Anabtawi Contribution (%)", readonly=True)
    provider_commission_amount = fields.Monetary(string="Provider Commission Amount", readonly=True)
    talabat_contribution_amount = fields.Monetary(string="Talabat Contribution Amount", readonly=True)
    anabtawi_contribution_amount = fields.Monetary(string="Anabtawi Contribution Amount", readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True)
    config_id = fields.Many2one("pos.config", string="Point of Sale", readonly=True)
    session_id = fields.Many2one("pos.session", string="Session", readonly=True)
    user_id = fields.Many2one("res.users", string="Cashier", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    l.id AS id,
                    s.date_order AS date_order,
                    s.id AS order_id,
                    s.customer_id_number AS talabat_id,
                    s.pricelist_id AS pricelist_id,
                    l.product_id AS product_id,
                    '' AS tax_names,
                    l.qty AS qty,
                    pt.uom_id AS product_uom_id,
                    l.discount AS applied_discount,
                    l.price_unit AS unit_price,
                    l.price_subtotal AS total_excluded,
                    l.price_subtotal_incl AS total_included,
                    ((l.qty * l.price_unit) * (l.discount / 100.0)) AS discount_amount,
                    0.0 AS provider_commission,
                    0.0 AS talabat_contribution,
                    0.0 AS anabtawi_contribution,
                    0.0 AS provider_commission_amount,
                    0.0 AS talabat_contribution_amount,
                    0.0 AS anabtawi_contribution_amount,
                    s.company_id AS company_id,
                    s.currency_id AS currency_id,
                    ps.config_id AS config_id,
                    s.session_id AS session_id,
                    s.user_id AS user_id
                FROM pos_order_line l
                JOIN pos_order s ON s.id = l.order_id
                JOIN product_pricelist pp ON pp.id = s.pricelist_id
                LEFT JOIN product_product p ON p.id = l.product_id
                LEFT JOIN product_template pt ON pt.id = p.product_tmpl_id
                LEFT JOIN pos_session ps ON ps.id = s.session_id
                WHERE pp.is_provider IS TRUE
            )
        """ % self._table)
