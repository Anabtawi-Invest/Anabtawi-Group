# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class OnlineCampaignDashboard(models.AbstractModel):
    _name = "online.campaign.dashboard"
    _description = "Online Campaign Executive Dashboard Backend"

    @api.model
    def get_dashboard_data(self, date_from=False, date_to=False, aggregator_id=False, campaign_id=False, config_ids=False):
        company_id = self.env.company.id

        # 1. Fetch available filter options
        all_aggregators = self.env["online.campaign.aggregator"].search_read(
            [("company_id", "=", company_id), ("active", "=", True)],
            ["id", "name"]
        )
        all_campaigns = self.env["online.discount.campaign"].search_read(
            [("company_id", "=", company_id)],
            ["id", "name"]
        )
        all_branches = self.env["pos.config"].search_read(
            [("company_id", "=", company_id)],
            ["id", "name"]
        )

        # 2. Build WHERE clause params for SQL queries
        where_order_clauses = ["po.company_id = %s", "po.state IN ('paid', 'done')"]
        order_params = [company_id]

        if date_from:
            where_order_clauses.append("po.date_order >= %s")
            order_params.append(date_from)
        if date_to:
            where_order_clauses.append("po.date_order <= %s")
            order_params.append(date_to)

        if config_ids:
            if isinstance(config_ids, int):
                config_ids = [config_ids]
            where_order_clauses.append("po.config_id IN %s")
            order_params.append(tuple(config_ids))

        where_order_str = " AND ".join(where_order_clauses)

        # Query total store sales across all channels
        query_store_sales = f"""
            SELECT COALESCE(SUM(po.amount_total), 0.0) AS total_store_sales,
                   COUNT(po.id) AS total_store_orders
              FROM pos_order po
             WHERE {where_order_str}
        """
        self.env.cr.execute(query_store_sales, order_params)
        store_res = self.env.cr.dictfetchone() or {}
        total_store_sales = float(store_res.get("total_store_sales", 0.0))
        total_store_orders = int(store_res.get("total_store_orders", 0))

        # 3. Query performance report data (Aggregator sales & campaign metrics)
        report_domain = [("company_id", "=", company_id)]
        if date_from:
            report_domain.append(("date", ">=", date_from[:10]))
        if date_to:
            report_domain.append(("date", "<=", date_to[:10]))
        if aggregator_id:
            report_domain.append(("aggregator_id", "=", int(aggregator_id)))
        if campaign_id:
            report_domain.append(("campaign_id", "=", int(campaign_id)))
        if config_ids:
            report_domain.append(("config_id", "in", config_ids))

        reports = self.env["online.campaign.performance.report"].search(report_domain)

        aggregator_sales = sum(reports.mapped("gross_amount"))
        order_count = sum(reports.mapped("order_count"))
        discount_amount = sum(reports.mapped("discount_amount"))
        company_contribution = sum(reports.mapped("company_contribution"))
        aggregator_contribution = sum(reports.mapped("aggregator_contribution"))
        estimated_commission = sum(reports.mapped("estimated_commission"))
        customer_collections = sum(reports.mapped("customer_collections"))
        estimated_net_proceeds = sum(reports.mapped("estimated_net_proceeds"))
        estimated_campaign_cost = sum(reports.mapped("estimated_campaign_cost"))

        aggregator_share_percent = (
            round((aggregator_sales / total_store_sales * 100.0), 2)
            if total_store_sales > 0
            else 0.0
        )
        avg_order_value = (
            round((aggregator_sales / order_count), 3)
            if order_count > 0
            else 0.0
        )

        kpis = {
            "total_store_sales": total_store_sales,
            "total_store_orders": total_store_orders,
            "aggregator_sales": aggregator_sales,
            "aggregator_share_percent": aggregator_share_percent,
            "order_count": order_count,
            "avg_order_value": avg_order_value,
            "discount_amount": discount_amount,
            "company_contribution": company_contribution,
            "aggregator_contribution": aggregator_contribution,
            "estimated_commission": estimated_commission,
            "customer_collections": customer_collections,
            "estimated_net_proceeds": estimated_net_proceeds,
            "estimated_campaign_cost": estimated_campaign_cost,
        }

        # 4. Aggregator Breakdown Table
        aggregators_dict = {}
        for r in reports:
            agg_id = r.aggregator_id.id if r.aggregator_id else 0
            agg_name = r.aggregator_id.name if r.aggregator_id else _("Unassigned")
            if agg_id not in aggregators_dict:
                aggregators_dict[agg_id] = {
                    "id": agg_id,
                    "name": agg_name,
                    "gross_amount": 0.0,
                    "order_count": 0,
                    "discount_amount": 0.0,
                    "company_contribution": 0.0,
                    "aggregator_contribution": 0.0,
                    "estimated_commission": 0.0,
                    "customer_collections": 0.0,
                    "estimated_net_proceeds": 0.0,
                    "store_share_percent": 0.0,
                }
            aggregators_dict[agg_id]["gross_amount"] += r.gross_amount
            aggregators_dict[agg_id]["order_count"] += r.order_count
            aggregators_dict[agg_id]["discount_amount"] += r.discount_amount
            aggregators_dict[agg_id]["company_contribution"] += r.company_contribution
            aggregators_dict[agg_id]["aggregator_contribution"] += r.aggregator_contribution
            aggregators_dict[agg_id]["estimated_commission"] += r.estimated_commission
            aggregators_dict[agg_id]["customer_collections"] += r.customer_collections
            aggregators_dict[agg_id]["estimated_net_proceeds"] += r.estimated_net_proceeds

        aggregators_list = list(aggregators_dict.values())
        for agg in aggregators_list:
            agg["store_share_percent"] = (
                round((agg["gross_amount"] / total_store_sales * 100.0), 2)
                if total_store_sales > 0
                else 0.0
            )

        aggregators_list.sort(key=lambda x: x["gross_amount"], reverse=True)

        # 5. Campaign Breakdown Table
        campaigns_dict = {}
        for r in reports:
            if not r.campaign_id:
                continue
            camp_id = r.campaign_id.id
            camp_name = r.campaign_id.name
            if camp_id not in campaigns_dict:
                campaigns_dict[camp_id] = {
                    "id": camp_id,
                    "name": camp_name,
                    "aggregator_name": r.aggregator_id.name if r.aggregator_id else "",
                    "gross_amount": 0.0,
                    "order_count": 0,
                    "discount_amount": 0.0,
                    "company_contribution": 0.0,
                    "aggregator_contribution": 0.0,
                    "estimated_commission": 0.0,
                    "estimated_net_proceeds": 0.0,
                }
            campaigns_dict[camp_id]["gross_amount"] += r.gross_amount
            campaigns_dict[camp_id]["order_count"] += r.order_count
            campaigns_dict[camp_id]["discount_amount"] += r.discount_amount
            campaigns_dict[camp_id]["company_contribution"] += r.company_contribution
            campaigns_dict[camp_id]["aggregator_contribution"] += r.aggregator_contribution
            campaigns_dict[camp_id]["estimated_commission"] += r.estimated_commission
            campaigns_dict[camp_id]["estimated_net_proceeds"] += r.estimated_net_proceeds

        campaigns_list = list(campaigns_dict.values())
        campaigns_list.sort(key=lambda x: x["gross_amount"], reverse=True)

        return {
            "date_from": date_from,
            "date_to": date_to,
            "all_aggregators": all_aggregators,
            "all_campaigns": all_campaigns,
            "all_branches": all_branches,
            "kpis": kpis,
            "aggregators": aggregators_list,
            "campaigns": campaigns_list,
        }

    @api.model
    def open_kpi_drilldown(self, metric_type=False, date_from=False, date_to=False, aggregator_id=False, campaign_id=False, config_ids=False):
        domain = [("company_id", "=", self.env.company.id)]
        if date_from:
            domain.append(("date", ">=", date_from[:10]))
        if date_to:
            domain.append(("date", "<=", date_to[:10]))
        if aggregator_id:
            domain.append(("aggregator_id", "=", int(aggregator_id)))
        if campaign_id:
            domain.append(("campaign_id", "=", int(campaign_id)))
        if config_ids:
            domain.append(("config_id", "in", config_ids))

        if metric_type == "store_sales":
            pos_domain = [("company_id", "=", self.env.company.id), ("state", "in", ["paid", "done"])]
            if date_from:
                pos_domain.append(("date_order", ">=", date_from))
            if date_to:
                pos_domain.append(("date_order", "<=", date_to))
            if config_ids:
                pos_domain.append(("config_id", "in", config_ids))
            return {
                "name": _("All POS Store Sales Orders"),
                "type": "ir.actions.act_window",
                "res_model": "pos.order",
                "view_mode": "list,pivot,form",
                "domain": pos_domain,
            }

        return {
            "name": _("Aggregator Performance Drilldown"),
            "type": "ir.actions.act_window",
            "res_model": "online.campaign.performance.report",
            "view_mode": "list,pivot,graph",
            "domain": domain,
        }
