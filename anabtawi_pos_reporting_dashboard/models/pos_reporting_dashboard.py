# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import datetime, time, timedelta

from odoo import _, api, fields, models

PAYMENT_METHOD_TALABAT = 142
PAYMENT_METHOD_CAREEM = 143
PAYMENT_METHOD_MYTHINGS = 144
PAYMENT_METHOD_KABSEH = 145


class PosReportingDashboard(models.TransientModel):
    _name = "pos.reporting.dashboard"
    _description = "POS Executive Reporting & Dashboard Service"

    @api.model
    def get_dashboard_data(self, date_from=None, date_to=None, config_ids=None):
        """
        Fetch executive dashboard metrics for specified date range and branch configs.
        Returns KPIs, per-branch comparison matrix, channel breakdown, and trend data.
        """
        # 1. Parse Date Bounds
        today = fields.Date.context_today(self)
        d_from = fields.Date.from_string(date_from) if date_from else today
        d_to = fields.Date.from_string(date_to) if date_to else today

        dt_start = datetime.combine(d_from, time.min)
        dt_end = datetime.combine(d_to, time.max)
        str_start = fields.Datetime.to_string(dt_start)
        str_end = fields.Datetime.to_string(dt_end)

        # 2. Identify Target Branches (pos.config)
        config_domain = [("active", "=", True)]
        if config_ids and isinstance(config_ids, (list, tuple)) and len(config_ids) > 0:
            config_domain.append(("id", "in", config_ids))

        configs = self.env["pos.config"].search(config_domain, order="name")
        active_config_ids = set(configs.ids)

        # 3. Gather Relevant POS Sessions
        session_domain = [
            ("config_id", "in", list(active_config_ids)),
            "|",
            "&", ("start_at", ">=", str_start), ("start_at", "<=", str_end),
            "&", ("stop_at", ">=", str_start), ("stop_at", "<=", str_end),
        ]
        sessions = self.env["pos.session"].search(session_domain)
        session_ids = sessions.ids

        # Structure per-branch data repository
        def _empty_branch_dict():
            return {
                "sales": 0.0,
                "cash": 0.0,
                "visa": 0.0,
                "hospitality": 0.0,
                "talabat": 0.0,
                "careem": 0.0,
                "mythings": 0.0,
                "kabseh": 0.0,
                "other_sales": 0.0,
                "cash_in": 0.0,
                "cash_out": 0.0,
                "net_cash_moves": 0.0,
                "rahen_in": 0.0,
                "rahen_out": 0.0,
                "net_pledges": 0.0,
                "advance_deposits": 0.0,
                "delivery_amount": 0.0,
                "order_count": 0,
            }

        branch_data = defaultdict(_empty_branch_dict)

        # --- A. Collect POS Payments & Sales ---
        if session_ids:
            payments = self.env["pos.payment"].search([("session_id", "in", session_ids)])
            for pay in payments:
                cfg_id = pay.session_id.config_id.id
                amt = pay.amount or 0.0
                branch_data[cfg_id]["sales"] += amt

                pm = pay.payment_method_id
                pm_id = pm.id
                pm_type = getattr(pm, "type", "")
                daily_type = getattr(pm, "daily_ops_report_type", "")
                pm_name = (pm.name or "").lower()

                # Payment Classification
                if daily_type == "cash" or pm_type == "cash" or "cash" in pm_name or "نقد" in pm_name:
                    branch_data[cfg_id]["cash"] += amt
                elif daily_type == "visa" or pm_type in ("bank", "pay_later") or "visa" in pm_name or "بطاقة" in pm_name or "card" in pm_name:
                    branch_data[cfg_id]["visa"] += amt
                elif daily_type == "hospitality" or "hospitality" in pm_name or "ضيافة" in pm_name:
                    branch_data[cfg_id]["hospitality"] += amt
                else:
                    branch_data[cfg_id]["other_sales"] += amt

                # Delivery Apps Specifics
                if pm_id == PAYMENT_METHOD_TALABAT or "talabat" in pm_name:
                    branch_data[cfg_id]["talabat"] += amt
                elif pm_id == PAYMENT_METHOD_CAREEM or "careem" in pm_name:
                    branch_data[cfg_id]["careem"] += amt
                elif pm_id == PAYMENT_METHOD_MYTHINGS or "mythings" in pm_name:
                    branch_data[cfg_id]["mythings"] += amt
                elif pm_id == PAYMENT_METHOD_KABSEH or "kabseh" in pm_name:
                    branch_data[cfg_id]["kabseh"] += amt

            # Order count & delivery amounts
            for sess in sessions:
                cfg_id = sess.config_id.id
                branch_data[cfg_id]["delivery_amount"] += getattr(sess, "delivery_amount", 0.0) or 0.0
                branch_data[cfg_id]["order_count"] += len(sess.order_ids)

        # --- B. Collect Cash In & Cash Out Moves (Statement Lines) ---
        if session_ids:
            st_lines = self.env["account.bank.statement.line"].search([
                ("pos_session_id", "in", session_ids),
            ])
            for st in st_lines:
                cfg_id = st.pos_session_id.config_id.id
                amt = st.amount or 0.0
                if amt > 0:
                    branch_data[cfg_id]["cash_in"] += amt
                else:
                    branch_data[cfg_id]["cash_out"] += abs(amt)

        # Compute net cash moves
        for cfg_id in active_config_ids:
            branch_data[cfg_id]["net_cash_moves"] = (
                branch_data[cfg_id]["cash_in"] - branch_data[cfg_id]["cash_out"]
            )

        # --- C. Collect Pledges (Rahen In & Rahen Out) ---
        # 1. Check pos.advance.order.pledge
        if "pos.advance.order.pledge" in self.env:
            pledges_adv = self.env["pos.advance.order.pledge"].search([
                "|",
                "&", ("pos_order_id", "!=", False),
                     ("pos_order_id.date_order", ">=", str_start),
                     ("pos_order_id.date_order", "<=", str_end),
                "&", ("order_id", "!=", False),
                     ("order_id.create_date", ">=", str_start),
                     ("order_id.create_date", "<=", str_end),
            ])
            for pledge in pledges_adv:
                cfg_id = False
                if pledge.pos_order_id:
                    cfg_id = pledge.pos_order_id.config_id.id
                elif pledge.order_id and hasattr(pledge.order_id, "pos_config_id"):
                    cfg_id = pledge.order_id.pos_config_id.id
                if not cfg_id or cfg_id not in active_config_ids:
                    continue

                amt = pledge.pledge_subtotal or getattr(pledge, "pledge_amount", 0.0) or 0.0
                if pledge.state == "active":
                    branch_data[cfg_id]["rahen_in"] += amt
                elif pledge.state == "returned":
                    branch_data[cfg_id]["rahen_out"] += amt

        # 2. Check standard pos.pledge
        if "pos.pledge" in self.env:
            pledges_std = self.env["pos.pledge"].search([
                ("create_date", ">=", str_start),
                ("create_date", "<=", str_end),
            ])
            for pledge in pledges_std:
                cfg_id = pledge.pos_config_id.id if pledge.pos_config_id else False
                if not cfg_id and pledge.pos_order_id:
                    cfg_id = pledge.pos_order_id.config_id.id
                if not cfg_id or cfg_id not in active_config_ids:
                    continue

                amt = pledge.pledge_amount or 0.0
                if pledge.state == "active":
                    branch_data[cfg_id]["rahen_in"] += amt
                elif pledge.state == "returned":
                    branch_data[cfg_id]["rahen_out"] += amt

        # Compute net pledges
        for cfg_id in active_config_ids:
            branch_data[cfg_id]["net_pledges"] = (
                branch_data[cfg_id]["rahen_in"] - branch_data[cfg_id]["rahen_out"]
            )

        # --- D. Collect Advance Orders & Deposits ---
        if "pos.advance.order" in self.env:
            adv_orders = self.env["pos.advance.order"].search([
                ("create_date", ">=", str_start),
                ("create_date", "<=", str_end),
                ("state", "not in", ("draft", "cancel")),
            ])
            for adv in adv_orders:
                cfg_id = adv.pos_config_id.id if adv.pos_config_id else (adv.from_pos_config_id.id if hasattr(adv, "from_pos_config_id") else False)
                if not cfg_id or cfg_id not in active_config_ids:
                    continue
                branch_data[cfg_id]["advance_deposits"] += adv.advance_amount or 0.0

        # --- E. Format Per-Branch Rows & Calculate Global Totals ---
        branch_rows = []
        global_totals = _empty_branch_dict()

        for config in configs:
            vals = branch_data[config.id]
            row = {
                "config_id": config.id,
                "branch_name": config.name,
                **vals,
            }
            branch_rows.append(row)

            for key in global_totals.keys():
                global_totals[key] += vals[key]

        # --- F. Build Channel Distribution & Daily Trends ---
        channels = [
            {"name": _("Cash Sales"), "value": global_totals["cash"], "color": "#28a745"},
            {"name": _("Visa / Card"), "value": global_totals["visa"], "color": "#007bff"},
            {"name": _("Hospitality"), "value": global_totals["hospitality"], "color": "#ffc107"},
            {"name": _("Talabat"), "value": global_totals["talabat"], "color": "#fd7e14"},
            {"name": _("Careem"), "value": global_totals["careem"], "color": "#20c997"},
            {"name": _("Mythings"), "value": global_totals["mythings"], "color": "#6f42c1"},
            {"name": _("Kabseh"), "value": global_totals["kabseh"], "color": "#e83e8c"},
            {"name": _("Other Channels"), "value": global_totals["other_sales"], "color": "#6c757d"},
        ]
        # Filter out 0 value channels for clean chart presentation
        channels_filtered = [c for c in channels if c["value"] > 0]

        # Daily Trend calculation (group by day)
        trend_days = []
        curr_date = d_from
        while curr_date <= d_to:
            day_str_start = fields.Datetime.to_string(datetime.combine(curr_date, time.min))
            day_str_end = fields.Datetime.to_string(datetime.combine(curr_date, time.max))

            day_payments = self.env["pos.payment"].search([
                ("session_id.config_id", "in", list(active_config_ids)),
                ("payment_date", ">=", day_str_start),
                ("payment_date", "<=", day_str_end),
            ])

            day_total = sum(p.amount or 0.0 for p in day_payments)
            day_cash = sum(
                p.amount or 0.0 for p in day_payments
                if (getattr(p.payment_method_id, "daily_ops_report_type", "") == "cash" or
                    getattr(p.payment_method_id, "type", "") == "cash" or
                    "cash" in (p.payment_method_id.name or "").lower())
            )
            day_visa = day_total - day_cash

            trend_days.append({
                "date": curr_date.strftime("%Y-%m-%d"),
                "date_label": curr_date.strftime("%b %d"),
                "total_sales": day_total,
                "cash_sales": day_cash,
                "visa_sales": day_visa,
            })
            curr_date += timedelta(days=1)

        all_configs = self.env["pos.config"].search([("active", "=", True)], order="name")
        all_branches_list = [{"id": cfg.id, "name": cfg.name} for cfg in all_configs]

        return {
            "date_from": d_from.strftime("%Y-%m-%d"),
            "date_to": d_to.strftime("%Y-%m-%d"),
            "active_branches_count": len(configs),
            "all_branches": all_branches_list,
            "kpis": {
                "total_sales": global_totals["sales"],
                "cash_sales": global_totals["cash"],
                "visa_sales": global_totals["visa"],
                "hospitality_sales": global_totals["hospitality"],
                "cash_in": global_totals["cash_in"],
                "cash_out": global_totals["cash_out"],
                "net_cash_moves": global_totals["net_cash_moves"],
                "rahen_in": global_totals["rahen_in"],
                "rahen_out": global_totals["rahen_out"],
                "net_pledges": global_totals["net_pledges"],
                "advance_deposits": global_totals["advance_deposits"],
                "delivery_amount": global_totals["delivery_amount"],
                "order_count": global_totals["order_count"],
            },
            "branches": branch_rows,
            "global_totals": global_totals,
            "channels": channels_filtered,
            "trends": trend_days,
        }
