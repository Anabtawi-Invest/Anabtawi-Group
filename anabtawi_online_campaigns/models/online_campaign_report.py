from odoo import fields, models, tools


class OnlineCampaignPerformanceReport(models.Model):
    _name = "online.campaign.performance.report"
    _description = "Online Campaign Profitability"
    _auto = False
    _order = "date desc, aggregator_id, campaign_id"

    date = fields.Date(readonly=True)
    aggregator_id = fields.Many2one("online.campaign.aggregator", readonly=True)
    campaign_id = fields.Many2one("online.discount.campaign", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
    session_id = fields.Many2one("pos.session", readonly=True)
    order_count = fields.Integer(readonly=True)
    line_count = fields.Integer(readonly=True)
    gross_amount = fields.Monetary(readonly=True, currency_field="currency_id")
    discount_amount = fields.Monetary(readonly=True, currency_field="currency_id")
    aggregator_contribution = fields.Monetary(readonly=True, currency_field="currency_id")
    company_contribution = fields.Monetary(readonly=True, currency_field="currency_id")
    estimated_commission = fields.Monetary(readonly=True, currency_field="currency_id")
    customer_collections = fields.Monetary(readonly=True, currency_field="currency_id")
    estimated_net_proceeds = fields.Monetary(readonly=True, currency_field="currency_id")
    estimated_campaign_cost = fields.Monetary(readonly=True, currency_field="currency_id")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    ROW_NUMBER() OVER (
                        ORDER BY DATE(po.date_order), pol.online_aggregator_id,
                                 pol.online_campaign_id, po.session_id
                    ) AS id,
                    DATE(po.date_order) AS date,
                    pol.online_aggregator_id AS aggregator_id,
                    pol.online_campaign_id AS campaign_id,
                    po.company_id AS company_id,
                    pc.currency_id AS currency_id,
                    po.session_id AS session_id,
                    COUNT(DISTINCT po.id) AS order_count,
                    COUNT(pol.id) AS line_count,
                    SUM(
                        CASE WHEN pol.qty * pol.price_unit < 0 THEN -1 ELSE 1 END
                        * pol.online_gross_amount
                    ) AS gross_amount,
                    SUM(
                        CASE WHEN pol.qty * pol.price_unit < 0 THEN -1 ELSE 1 END
                        * pol.online_discount_amount
                    ) AS discount_amount,
                    SUM(
                        CASE WHEN pol.qty * pol.price_unit < 0 THEN -1 ELSE 1 END
                        * pol.aggregator_contribution_amount
                    ) AS aggregator_contribution,
                    SUM(
                        CASE WHEN pol.qty * pol.price_unit < 0 THEN -1 ELSE 1 END
                        * pol.company_contribution_amount
                    ) AS company_contribution,
                    SUM(
                        CASE WHEN pol.qty * pol.price_unit < 0 THEN -1 ELSE 1 END
                        * pol.aggregator_commission_amount
                    ) AS estimated_commission,
                    SUM(
                        CASE WHEN pol.qty * pol.price_unit < 0 THEN -1 ELSE 1 END
                        * pol.online_customer_paid_amount
                    ) AS customer_collections,
                    SUM(
                        CASE WHEN pol.qty * pol.price_unit < 0 THEN -1 ELSE 1 END
                        * (
                            pol.online_customer_paid_amount
                            + pol.aggregator_contribution_amount
                            - pol.aggregator_commission_amount
                        )
                    ) AS estimated_net_proceeds,
                    SUM(
                        CASE WHEN pol.qty * pol.price_unit < 0 THEN -1 ELSE 1 END
                        * (
                            pol.company_contribution_amount
                            + pol.aggregator_commission_amount
                        )
                    ) AS estimated_campaign_cost
                FROM pos_order_line pol
                JOIN pos_order po ON po.id = pol.order_id
                JOIN pos_config pc ON pc.id = po.config_id
                WHERE pol.online_campaign_id IS NOT NULL
                  AND po.state IN ('paid', 'done')
                GROUP BY
                    DATE(po.date_order), pol.online_aggregator_id,
                    pol.online_campaign_id, po.company_id, pc.currency_id, po.session_id
            )
        """)



class OnlineAggregatorSalesReport(models.Model):
    _name = "online.aggregator.sales.report"
    _description = "Aggregator Sales from POS Payment Methods"
    _auto = False
    _order = "date desc, aggregator_id, config_id"

    date = fields.Date(readonly=True)
    aggregator_id = fields.Many2one("online.campaign.aggregator", readonly=True)
    payment_method_id = fields.Many2one("pos.payment.method", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
    config_id = fields.Many2one("pos.config", string="Point of Sale", readonly=True)
    session_id = fields.Many2one("pos.session", readonly=True)
    order_count = fields.Integer(readonly=True)
    payment_amount = fields.Monetary(readonly=True, currency_field="currency_id")
    gross_sales = fields.Monetary(readonly=True, currency_field="currency_id")
    tax_amount = fields.Monetary(readonly=True, currency_field="currency_id")
    discount_amount = fields.Monetary(readonly=True, currency_field="currency_id")
    campaign_sales = fields.Monetary(readonly=True, currency_field="currency_id")
    normal_sales = fields.Monetary(readonly=True, currency_field="currency_id")
    aggregator_contribution = fields.Monetary(readonly=True, currency_field="currency_id")
    company_contribution = fields.Monetary(readonly=True, currency_field="currency_id")
    commission_percent = fields.Float(readonly=True, digits=(16, 4))
    estimated_commission = fields.Monetary(readonly=True, currency_field="currency_id")
    estimated_settlement_amount = fields.Monetary(readonly=True, currency_field="currency_id")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                WITH order_campaign AS (
                    SELECT
                        pol.order_id,
                        SUM(pol.online_discount_amount) AS discount_amount,
                        SUM(pol.aggregator_contribution_amount) AS aggregator_contribution,
                        SUM(pol.company_contribution_amount) AS company_contribution,
                        SUM(CASE WHEN pol.online_campaign_id IS NOT NULL THEN ABS(pol.price_subtotal_incl) ELSE 0 END) AS campaign_sales
                    FROM pos_order_line pol
                    GROUP BY pol.order_id
                )
                SELECT
                    ROW_NUMBER() OVER (
                        ORDER BY DATE(po.date_order), agg.id, pp.payment_method_id, po.config_id, po.session_id
                    ) AS id,
                    DATE(po.date_order) AS date,
                    agg.id AS aggregator_id,
                    pp.payment_method_id AS payment_method_id,
                    po.company_id AS company_id,
                    pc.currency_id AS currency_id,
                    po.config_id AS config_id,
                    po.session_id AS session_id,
                    COUNT(DISTINCT po.id) AS order_count,
                    SUM(pp.amount) AS payment_amount,
                    SUM(pp.amount) AS gross_sales,
                    SUM(po.amount_tax * CASE WHEN po.amount_total = 0 THEN 0 ELSE pp.amount / po.amount_total END) AS tax_amount,
                    SUM(COALESCE(oc.discount_amount, 0.0) * CASE WHEN po.amount_total = 0 THEN 0 ELSE pp.amount / po.amount_total END) AS discount_amount,
                    SUM(COALESCE(oc.campaign_sales, 0.0) * CASE WHEN po.amount_total = 0 THEN 0 ELSE pp.amount / po.amount_total END) AS campaign_sales,
                    SUM((po.amount_total - COALESCE(oc.campaign_sales, 0.0)) * CASE WHEN po.amount_total = 0 THEN 0 ELSE pp.amount / po.amount_total END) AS normal_sales,
                    SUM(COALESCE(oc.aggregator_contribution, 0.0) * CASE WHEN po.amount_total = 0 THEN 0 ELSE pp.amount / po.amount_total END) AS aggregator_contribution,
                    SUM(COALESCE(oc.company_contribution, 0.0) * CASE WHEN po.amount_total = 0 THEN 0 ELSE pp.amount / po.amount_total END) AS company_contribution,
                    agg.default_commission_percent AS commission_percent,
                    SUM(pp.amount * agg.default_commission_percent / 100.0) AS estimated_commission,
                    SUM(pp.amount + (COALESCE(oc.aggregator_contribution, 0.0) * CASE WHEN po.amount_total = 0 THEN 0 ELSE pp.amount / po.amount_total END) - (pp.amount * agg.default_commission_percent / 100.0)) AS estimated_settlement_amount
                FROM pos_payment pp
                JOIN pos_order po ON po.id = pp.pos_order_id
                JOIN pos_config pc ON pc.id = po.config_id
                JOIN online_campaign_aggregator_payment_method_rel rel ON rel.payment_method_id = pp.payment_method_id
                JOIN online_campaign_aggregator agg ON agg.id = rel.aggregator_id
                LEFT JOIN order_campaign oc ON oc.order_id = po.id
                WHERE po.state IN ('paid', 'done')
                GROUP BY
                    DATE(po.date_order), agg.id, pp.payment_method_id, po.company_id,
                    pc.currency_id, po.config_id, po.session_id, agg.default_commission_percent
            )
        """)
