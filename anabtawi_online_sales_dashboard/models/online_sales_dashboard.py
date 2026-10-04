# -*- coding: utf-8 -*-
from datetime import datetime, date, timedelta
from collections import defaultdict
import logging

from odoo import models, fields, api, _
from odoo.tools import float_round

_logger = logging.getLogger(__name__)


class OnlineSalesDashboard(models.TransientModel):
    _name = "online.sales.dashboard"
    _description = "Online Sales & Delivery Analytics Dashboard"

    @api.model
    def _get_channel_mapping(self):
        """Build keyword and payment method lookup maps for online channels."""
        channels = self.env["online.sales.channel"].sudo().search([("active", "=", True)])
        if not channels:
            self.env["online.sales.channel"].create_default_channels()
            channels = self.env["online.sales.channel"].sudo().search([("active", "=", True)])

        channel_list = []
        for ch in channels:
            kw_set = set()
            if ch.keywords:
                for k in ch.keywords.split(","):
                    if k.strip():
                        kw_set.add(k.strip().lower())
            
            pm_ids = set(ch.payment_method_ids.ids)
            channel_list.append({
                "id": ch.id,
                "name": ch.name,
                "code": ch.code,
                "color": ch.color or "#0083B0",
                "commission_rate": ch.commission_rate or 0.0,
                "keywords": kw_set,
                "pm_ids": pm_ids,
            })
        return channel_list

    @api.model
    def _classify_order_channel(self, order, channel_list):
        """Classify a POS/Sale order into an online channel."""
        # 1. Match explicitly linked payment method on POS Order
        if hasattr(order, "payment_ids") and order.payment_ids:
            for p in order.payment_ids:
                pm = p.payment_method_id
                pm_id = pm.id
                pm_name = (pm.name or "").lower().strip()
                
                # Match linked PMs first
                for ch in channel_list:
                    if pm_id in ch["pm_ids"]:
                        return ch
                
                # Match keywords in PM name
                for ch in channel_list:
                    if any(k in pm_name for k in ch["keywords"]):
                        return ch

        # 2. Match POS Daily Operation Type / Notes / Tag
        note_str = (getattr(order, "note", "") or getattr(order, "pos_reference", "") or "").lower()
        for ch in channel_list:
            if any(k in note_str for k in ch["keywords"]):
                return ch

        # 3. Match Delivery / E-Commerce flags
        if getattr(order, "is_delivery", False) or getattr(order, "website_id", False):
            for ch in channel_list:
                if ch["code"] == "WEBSITE" or ch["code"] == "DIRECT_DELIVERY":
                    return ch

        # Fallback to General Delivery / Other Online
        for ch in channel_list:
            if ch["code"] == "DIRECT_DELIVERY":
                return ch
        return channel_list[0] if channel_list else {"id": 0, "name": "Other Online", "code": "OTHER", "color": "#757575", "commission_rate": 0.0}

    @api.model
    def get_online_dashboard_data(self, date_from=None, date_to=None, config_ids=None, channel_ids=None):
        """Main API endpoint returning all online sales metrics, charts, and channel breakdowns."""
        today = fields.Date.today()
        if not date_from:
            date_from = today.replace(day=1)
        else:
            date_from = fields.Date.to_date(date_from)

        if not date_to:
            date_to = today
        else:
            date_to = fields.Date.to_date(date_to)

        dt_start = datetime.combine(date_from, datetime.min.time())
        dt_end = datetime.combine(date_to, datetime.max.time())

        # Load channel configuration maps
        channel_list = self._get_channel_mapping()
        if channel_ids:
            channel_list = [c for c in channel_list if c["id"] in channel_ids]

        # Branch configs filter
        config_domain = [("active", "=", True)]
        if config_ids:
            config_domain.append(("id", "in", config_ids))
        pos_configs = self.env["pos.config"].sudo().search(config_domain)
        config_map = {cfg.id: cfg.name for cfg in pos_configs}

        # Query POS Orders matching online delivery criteria
        pos_order_domain = [
            ("date_order", ">=", dt_start),
            ("date_order", "<=", dt_end),
            ("state", "in", ["paid", "done", "invoiced"]),
        ]
        if config_ids:
            pos_order_domain.append(("config_id", "in", config_ids))

        pos_orders = self.env["pos.order"].sudo().search(pos_order_domain)

        # Filters for online orders specifically
        online_kw = {"talabat", "careem", "mythings", "ashyaty", "kabseh", "طلبات", "كريم", "أشياتي", "كبسة", "توصيل", "delivery", "online"}
        
        def _is_online_order(ord_rec):
            if getattr(ord_rec, "is_delivery", False):
                return True
            if hasattr(ord_rec, "payment_ids"):
                for p in ord_rec.payment_ids:
                    pm_name = (p.payment_method_id.name or "").lower()
                    if any(k in pm_name for k in online_kw):
                        return True
            note_str = (getattr(ord_rec, "note", "") or "").lower()
            if any(k in note_str for k in online_kw):
                return True
            return False

        online_pos_orders = [o for o in pos_orders if _is_online_order(o)]

        # Initialize Accumulators
        channel_stats = defaultdict(lambda: {"order_count": 0, "gross_amount": 0.0, "commission_amount": 0.0, "net_amount": 0.0})
        branch_stats = defaultdict(lambda: {"order_count": 0, "gross_amount": 0.0, "channels": defaultdict(float)})
        hourly_stats = defaultdict(lambda: {"order_count": 0, "gross_amount": 0.0})
        product_stats = defaultdict(lambda: {"qty": 0.0, "amount": 0.0, "product_name": ""})
        category_stats = defaultdict(lambda: {"amount": 0.0, "cat_name": ""})

        total_gross_sales = 0.0
        total_orders_count = len(online_pos_orders)
        total_commission_estimated = 0.0

        for order in online_pos_orders:
            ch_info = self._classify_order_channel(order, channel_list)
            ch_code = ch_info["code"]
            order_amt = order.amount_total or 0.0
            
            commission_rate = ch_info.get("commission_rate", 0.0)
            comm_amt = float_round(order_amt * (commission_rate / 100.0), precision_digits=3)
            net_amt = order_amt - comm_amt

            total_gross_sales += order_amt
            total_commission_estimated += comm_amt

            # Channel Level
            channel_stats[ch_code]["order_count"] += 1
            channel_stats[ch_code]["gross_amount"] += order_amt
            channel_stats[ch_code]["commission_amount"] += comm_amt
            channel_stats[ch_code]["net_amount"] += net_amt
            channel_stats[ch_code]["info"] = ch_info

            # Branch Level
            cfg_id = order.config_id.id if order.config_id else 0
            cfg_name = config_map.get(cfg_id, _("Main Branch"))
            branch_stats[cfg_name]["order_count"] += 1
            branch_stats[cfg_name]["gross_amount"] += order_amt
            branch_stats[cfg_name]["channels"][ch_info["name"]] += order_amt

            # Hourly Level
            if order.date_order:
                hour_str = f"{order.date_order.hour:02d}:00"
                hourly_stats[hour_str]["order_count"] += 1
                hourly_stats[hour_str]["gross_amount"] += order_amt

            # Product & Category Breakdown
            for line in order.lines:
                p_id = line.product_id.id if line.product_id else 0
                p_name = line.product_id.display_name if line.product_id else _("Unknown Item")
                p_qty = line.qty or 0.0
                p_amt = line.price_subtotal_incl or line.price_subtotal or 0.0

                product_stats[p_id]["qty"] += p_qty
                product_stats[p_id]["amount"] += p_amt
                product_stats[p_id]["product_name"] = p_name

                cat_name = line.product_id.pos_categ_id.name if (line.product_id and line.product_id.pos_categ_id) else _("General")
                category_stats[cat_name]["amount"] += p_amt
                category_stats[cat_name]["cat_name"] = cat_name

        # Calculate AOV (Average Order Value)
        avg_order_value = float_round(total_gross_sales / total_orders_count, precision_digits=3) if total_orders_count > 0 else 0.0
        net_sales = total_gross_sales - total_commission_estimated

        # Format Channel Breakdown Chart Data
        channel_chart_data = []
        for ch_code, s in channel_stats.items():
            ch_info = s["info"]
            pct = float_round((s["gross_amount"] / total_gross_sales * 100.0), precision_digits=1) if total_gross_sales > 0 else 0.0
            channel_chart_data.append({
                "code": ch_code,
                "name": ch_info["name"],
                "color": ch_info["color"],
                "gross_amount": float_round(s["gross_amount"], precision_digits=3),
                "commission_amount": float_round(s["commission_amount"], precision_digits=3),
                "net_amount": float_round(s["net_amount"], precision_digits=3),
                "order_count": s["order_count"],
                "percentage": pct,
            })
        channel_chart_data.sort(key=lambda x: x["gross_amount"], reverse=True)

        # Format Branch Chart Data
        branch_chart_data = []
        for b_name, b_data in branch_stats.items():
            branch_chart_data.append({
                "branch_name": b_name,
                "gross_amount": float_round(b_data["gross_amount"], precision_digits=3),
                "order_count": b_data["order_count"],
                "channels": {k: float_round(v, precision_digits=3) for k, v in b_data["channels"].items()},
            })
        branch_chart_data.sort(key=lambda x: x["gross_amount"], reverse=True)

        # Format Hourly Trend Data (00:00 to 23:00)
        hourly_chart_data = []
        for h in range(24):
            h_key = f"{h:02d}:00"
            h_info = hourly_stats.get(h_key, {"order_count": 0, "gross_amount": 0.0})
            hourly_chart_data.append({
                "hour": h_key,
                "gross_amount": float_round(h_info["gross_amount"], precision_digits=3),
                "order_count": h_info["order_count"],
            })

        # Format Top 10 Products
        top_products = sorted(product_stats.values(), key=lambda x: x["amount"], reverse=True)[:10]
        for p in top_products:
            p["amount"] = float_round(p["amount"], precision_digits=3)

        # Format Top Categories
        top_categories = sorted(category_stats.values(), key=lambda x: x["amount"], reverse=True)
        for c in top_categories:
            c["amount"] = float_round(c["amount"], precision_digits=3)

        top_channel_name = channel_chart_data[0]["name"] if channel_chart_data else _("None")
        top_branch_name = branch_chart_data[0]["branch_name"] if branch_chart_data else _("None")

        return {
            "summary": {
                "total_gross_sales": float_round(total_gross_sales, precision_digits=3),
                "total_commission": float_round(total_commission_estimated, precision_digits=3),
                "net_sales": float_round(net_sales, precision_digits=3),
                "total_orders_count": total_orders_count,
                "avg_order_value": avg_order_value,
                "top_channel": top_channel_name,
                "top_branch": top_branch_name,
                "currency": self.env.company.currency_id.symbol or "JOD",
            },
            "channel_breakdown": channel_chart_data,
            "branch_breakdown": branch_chart_data,
            "hourly_trend": hourly_chart_data,
            "top_products": top_products,
            "top_categories": top_categories,
        }

    @api.model
    def get_online_sales_drilldown(self, channel_code=None, branch_name=None, date_from=None, date_to=None):
        """Action handler to return underlying POS orders for interactive drill-down."""
        today = fields.Date.today()
        d_from = fields.Date.to_date(date_from) if date_from else today.replace(day=1)
        d_to = fields.Date.to_date(date_to) if date_to else today
        
        dt_start = datetime.combine(d_from, datetime.min.time())
        dt_end = datetime.combine(d_to, datetime.max.time())

        domain = [
            ("date_order", ">=", dt_start),
            ("date_order", "<=", dt_end),
            ("state", "in", ["paid", "done", "invoiced"]),
        ]

        if branch_name:
            cfg = self.env["pos.config"].sudo().search([("name", "=", branch_name)], limit=1)
            if cfg:
                domain.append(("config_id", "=", cfg.id))

        orders = self.env["pos.order"].sudo().search(domain)
        
        channel_list = self._get_channel_mapping()
        online_orders = []
        for o in orders:
            ch_info = self._classify_order_channel(o, channel_list)
            if not channel_code or ch_info["code"] == channel_code:
                online_orders.append(o.id)

        return {
            "name": _("Online Orders Drill-down"),
            "type": "ir.actions.act_window",
            "res_model": "pos.order",
            "view_mode": "tree,form",
            "domain": [("id", "in", online_orders)],
            "target": "current",
        }
