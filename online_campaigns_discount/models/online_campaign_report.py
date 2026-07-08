from odoo import fields, models, tools


class OnlineCampaignPerformanceReport(models.Model):
    _name = "online.campaign.performance.report"
    _description = "Online Aggregator Profitability"
    _auto = False
    _order = "date desc, aggregator_id, campaign_id"

    date = fields.Date(readonly=True)
    aggregator_id = fields.Many2one("online.campaign.aggregator", readonly=True)
    campaign_id = fields.Many2one("online.discount.campaign", readonly=True)
    is_campaign_order = fields.Boolean(string="Campaign Order", readonly=True)
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
                                 pol.online_campaign_id, po.session_id,
                                 (pol.online_campaign_id IS NOT NULL)
                    ) AS id,
                    DATE(po.date_order) AS date,
                    pol.online_aggregator_id AS aggregator_id,
                    pol.online_campaign_id AS campaign_id,
                    (pol.online_campaign_id IS NOT NULL) AS is_campaign_order,
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
                        * COALESCE(pol.online_discount_amount, 0.0)
                    ) AS discount_amount,
                    SUM(
                        CASE WHEN pol.qty * pol.price_unit < 0 THEN -1 ELSE 1 END
                        * COALESCE(pol.aggregator_contribution_amount, 0.0)
                    ) AS aggregator_contribution,
                    SUM(
                        CASE WHEN pol.qty * pol.price_unit < 0 THEN -1 ELSE 1 END
                        * COALESCE(pol.company_contribution_amount, 0.0)
                    ) AS company_contribution,
                    SUM(
                        CASE WHEN pol.qty * pol.price_unit < 0 THEN -1 ELSE 1 END
                        * COALESCE(pol.aggregator_commission_amount, 0.0)
                    ) AS estimated_commission,
                    SUM(
                        CASE WHEN pol.qty * pol.price_unit < 0 THEN -1 ELSE 1 END
                        * pol.online_customer_paid_amount
                    ) AS customer_collections,
                    SUM(
                        CASE WHEN pol.qty * pol.price_unit < 0 THEN -1 ELSE 1 END
                        * (
                            pol.online_customer_paid_amount
                            + COALESCE(pol.aggregator_contribution_amount, 0.0)
                            - COALESCE(pol.aggregator_commission_amount, 0.0)
                        )
                    ) AS estimated_net_proceeds,
                    SUM(
                        CASE WHEN pol.qty * pol.price_unit < 0 THEN -1 ELSE 1 END
                        * (
                            COALESCE(pol.company_contribution_amount, 0.0)
                            + COALESCE(pol.aggregator_commission_amount, 0.0)
                        )
                    ) AS estimated_campaign_cost
                FROM pos_order_line pol
                JOIN pos_order po ON po.id = pol.order_id
                JOIN pos_config pc ON pc.id = po.config_id
                WHERE pol.online_aggregator_id IS NOT NULL
                  AND po.state IN ('paid', 'done')
                GROUP BY
                    DATE(po.date_order), pol.online_aggregator_id,
                    pol.online_campaign_id, (pol.online_campaign_id IS NOT NULL),
                    po.company_id, pc.currency_id, po.session_id
            )
        """)
