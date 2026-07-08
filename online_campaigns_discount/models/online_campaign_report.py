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
                WITH campaign_rows AS (
                    SELECT
                        DATE(po.date_order) AS date,
                        pol.online_aggregator_id AS aggregator_id,
                        pol.online_campaign_id AS campaign_id,
                        TRUE AS is_campaign_order,
                        po.company_id AS company_id,
                        pc.currency_id AS currency_id,
                        po.session_id AS session_id,
                        po.id AS order_id,
                        COUNT(pol.id) AS line_count,
                        SUM((CASE WHEN pol.qty * pol.price_unit < 0 THEN -1 ELSE 1 END) * pol.online_gross_amount) AS gross_amount,
                        SUM((CASE WHEN pol.qty * pol.price_unit < 0 THEN -1 ELSE 1 END) * COALESCE(pol.online_discount_amount, 0.0)) AS discount_amount,
                        SUM((CASE WHEN pol.qty * pol.price_unit < 0 THEN -1 ELSE 1 END) * COALESCE(pol.aggregator_contribution_amount, 0.0)) AS aggregator_contribution,
                        SUM((CASE WHEN pol.qty * pol.price_unit < 0 THEN -1 ELSE 1 END) * COALESCE(pol.company_contribution_amount, 0.0)) AS company_contribution,
                        SUM((CASE WHEN pol.qty * pol.price_unit < 0 THEN -1 ELSE 1 END) * COALESCE(pol.aggregator_commission_amount, 0.0)) AS estimated_commission,
                        SUM((CASE WHEN pol.qty * pol.price_unit < 0 THEN -1 ELSE 1 END) * pol.online_customer_paid_amount) AS customer_collections
                    FROM pos_order_line pol
                    JOIN pos_order po ON po.id = pol.order_id
                    JOIN pos_config pc ON pc.id = po.config_id
                    WHERE pol.online_aggregator_id IS NOT NULL
                      AND pol.online_campaign_id IS NOT NULL
                      AND po.state IN ('paid', 'done')
                    GROUP BY DATE(po.date_order), pol.online_aggregator_id, pol.online_campaign_id,
                             po.company_id, pc.currency_id, po.session_id, po.id
                ),
                non_campaign_payment_rows AS (
                    SELECT
                        DATE(po.date_order) AS date,
                        pay.aggregator_id AS aggregator_id,
                        NULL::integer AS campaign_id,
                        FALSE AS is_campaign_order,
                        po.company_id AS company_id,
                        pc.currency_id AS currency_id,
                        po.session_id AS session_id,
                        po.id AS order_id,
                        COALESCE(line_counts.line_count, 0) AS line_count,
                        ABS(po.amount_total - po.amount_tax) AS gross_amount,
                        0.0 AS discount_amount,
                        0.0 AS aggregator_contribution,
                        0.0 AS company_contribution,
                        (
                            CASE
                                WHEN ag.commission_base = 'before_tax' THEN
                                    CASE
                                        WHEN ABS(po.amount_total) = 0 THEN 0.0
                                        ELSE ABS(pay.paid_amount) * ABS(po.amount_total - po.amount_tax) / ABS(po.amount_total)
                                    END
                                ELSE ABS(pay.paid_amount)
                            END
                        ) * ag.default_commission_percent / 100.0 AS estimated_commission,
                        pay.paid_amount AS customer_collections
                    FROM (
                        SELECT
                            pp.pos_order_id AS order_id,
                            rel.aggregator_id AS aggregator_id,
                            SUM(pp.amount) AS paid_amount
                        FROM pos_payment pp
                        JOIN online_campaign_aggregator_pos_payment_method_rel rel
                             ON rel.payment_method_id = pp.payment_method_id
                        GROUP BY pp.pos_order_id, rel.aggregator_id
                    ) pay
                    JOIN pos_order po ON po.id = pay.order_id
                    JOIN pos_config pc ON pc.id = po.config_id
                    JOIN online_campaign_aggregator ag ON ag.id = pay.aggregator_id
                    LEFT JOIN (
                        SELECT order_id, COUNT(id) AS line_count
                        FROM pos_order_line
                        GROUP BY order_id
                    ) line_counts ON line_counts.order_id = po.id
                    WHERE po.state IN ('paid', 'done')
                      AND ag.active = TRUE
                      AND ag.company_id = po.company_id
                      AND NOT EXISTS (
                          SELECT 1
                            FROM pos_order_line campaign_line
                           WHERE campaign_line.order_id = po.id
                             AND campaign_line.online_campaign_id IS NOT NULL
                      )
                )                ),
                all_rows AS (
                    SELECT * FROM campaign_rows
                    UNION ALL
                    SELECT * FROM non_campaign_payment_rows
                )
                SELECT
                    ROW_NUMBER() OVER (
                        ORDER BY date, aggregator_id, campaign_id, session_id, is_campaign_order
                    ) AS id,
                    date,
                    aggregator_id,
                    campaign_id,
                    is_campaign_order,
                    company_id,
                    currency_id,
                    session_id,
                    COUNT(DISTINCT order_id) AS order_count,
                    SUM(line_count) AS line_count,
                    SUM(gross_amount) AS gross_amount,
                    SUM(discount_amount) AS discount_amount,
                    SUM(aggregator_contribution) AS aggregator_contribution,
                    SUM(company_contribution) AS company_contribution,
                    SUM(estimated_commission) AS estimated_commission,
                    SUM(customer_collections) AS customer_collections,
                    SUM(customer_collections + aggregator_contribution - estimated_commission) AS estimated_net_proceeds,
                    SUM(company_contribution + estimated_commission) AS estimated_campaign_cost
                FROM all_rows
                GROUP BY date, aggregator_id, campaign_id, is_campaign_order,
                         company_id, currency_id, session_id
            )
        """)
