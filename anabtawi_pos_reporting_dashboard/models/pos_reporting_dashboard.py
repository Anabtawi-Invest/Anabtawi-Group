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

    def _parse_datetime_bounds(self, date_from, date_to):
        """Parse datetime parameters supporting both Date (YYYY-MM-DD) and Datetime (YYYY-MM-DD HH:MM:SS)."""
        today = fields.Date.context_today(self)

        def _to_dt(val, is_end=False):
            if not val:
                d = today
                return datetime.combine(d, time.max if is_end else time.min)
            if isinstance(val, datetime):
                return val
            val_str = str(val).strip()
            if " " in val_str or "T" in val_str:
                val_clean = val_str.replace("T", " ")
                try:
                    return datetime.strptime(val_clean.split(".")[0], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass
            d = fields.Date.from_string(val_str)
            return datetime.combine(d, time.max if is_end else time.min)

        dt_start = _to_dt(date_from, is_end=False)
        dt_end = _to_dt(date_to, is_end=True)
        return dt_start, dt_end

    @api.model
    def get_dashboard_data(self, date_from=None, date_to=None, config_ids=None):
        """
        Fetch executive dashboard metrics for specified datetime range and branch configs.
        Returns KPIs, per-branch comparison matrix, channel breakdown, and trend data.
        """
        # 1. Parse Datetime Bounds (with exact hour/minute/second precision)
        dt_start, dt_end = self._parse_datetime_bounds(date_from, date_to)
        str_start = fields.Datetime.to_string(dt_start)
        str_end = fields.Datetime.to_string(dt_end)

        # 2. Identify Target Branches (sudo to bypass multi-company rule restrictions)
        config_domain = [("active", "=", True)]
        if config_ids and isinstance(config_ids, (list, tuple)) and len(config_ids) > 0:
            config_domain.append(("id", "in", config_ids))

        configs = self.env["pos.config"].sudo().search(config_domain, order="name")
        active_config_ids = set(configs.ids)

        # Structure per-branch data repository
        def _empty_branch_dict():
            return {
                "sales": 0.0,
                "untaxed_sales": 0.0,
                "tax_amount": 0.0,
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
                "advance_order_count": 0,
                "advance_order_total": 0.0,
                "advance_pickup_value": 0.0,
                "advance_remaining_amount": 0.0,
                "advance_pending_count": 0,
                "delivery_amount": 0.0,
                "order_count": 0,
            }

        branch_data = defaultdict(_empty_branch_dict)

        # --- A. Collect POS Payments & Channel Breakdown ---
        payments = self.env["pos.payment"].sudo().search([
            ("session_id.config_id", "in", list(active_config_ids)),
            ("payment_date", ">=", str_start),
            ("payment_date", "<=", str_end),
        ])
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

        # --- B. Collect POS Orders (Untaxed, Tax, Order Count & Delivery) ---
        pos_orders = self.env["pos.order"].sudo().search([
            ("config_id", "in", list(active_config_ids)),
            ("state", "in", ("paid", "done", "invoiced")),
            ("date_order", ">=", str_start),
            ("date_order", "<=", str_end),
        ])
        for order in pos_orders:
            cfg_id = order.config_id.id
            branch_data[cfg_id]["untaxed_sales"] += order.amount_untaxed or 0.0
            branch_data[cfg_id]["tax_amount"] += order.amount_tax or 0.0
            branch_data[cfg_id]["delivery_amount"] += getattr(order, "delivery_amount", 0.0) or 0.0
            branch_data[cfg_id]["order_count"] += 1

        # --- C. Collect Cash In & Cash Out Moves (Statement Lines) ---
        st_lines = self.env["account.bank.statement.line"].sudo().search([
            ("pos_session_id.config_id", "in", list(active_config_ids)),
            ("date", ">=", dt_start.date()),
            ("date", "<=", dt_end.date()),
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

        # --- D. Collect Pledges (Rahen In & Rahen Out) ---
        # 1. pos.advance.order.pledge
        if "pos.advance.order.pledge" in self.env:
            # Rahen In (Received On timestamp in range)
            pledges_in = self.env["pos.advance.order.pledge"].sudo().search([
                ("state", "in", ("active", "returned")),
                "|",
                "&", ("receive_date", ">=", str_start), ("receive_date", "<=", str_end),
                "&", ("receive_date", "=", False),
                     "&", ("create_date", ">=", str_start), ("create_date", "<=", str_end),
            ])
            for pledge in pledges_in:
                cfg_id = False
                if pledge.pos_order_id:
                    cfg_id = pledge.pos_order_id.config_id.id
                elif pledge.order_id and hasattr(pledge.order_id, "pos_config_id"):
                    cfg_id = pledge.order_id.pos_config_id.id
                elif pledge.order_id and hasattr(pledge.order_id, "from_pos_config_id"):
                    cfg_id = pledge.order_id.from_pos_config_id.id

                if not cfg_id or cfg_id not in active_config_ids:
                    continue

                amt = (
                    pledge.pledge_subtotal
                    or (getattr(pledge, "pledge_qty", 1.0) * getattr(pledge, "pledge_amount_unit", 0.0))
                    or getattr(pledge, "pledge_amount", 0.0)
                    or 0.0
                )
                branch_data[cfg_id]["rahen_in"] += amt

            # Rahen Out (Returned On timestamp in range)
            pledges_out = self.env["pos.advance.order.pledge"].sudo().search([
                ("state", "=", "returned"),
                "|",
                "&", ("return_date", ">=", str_start), ("return_date", "<=", str_end),
                "&", ("return_date", "=", False),
                     "&", ("write_date", ">=", str_start), ("write_date", "<=", str_end),
            ])
            for pledge in pledges_out:
                cfg_id = False
                if pledge.pos_order_id:
                    cfg_id = pledge.pos_order_id.config_id.id
                elif pledge.order_id and hasattr(pledge.order_id, "pos_config_id"):
                    cfg_id = pledge.order_id.pos_config_id.id
                elif pledge.order_id and hasattr(pledge.order_id, "from_pos_config_id"):
                    cfg_id = pledge.order_id.from_pos_config_id.id

                if not cfg_id or cfg_id not in active_config_ids:
                    continue

                amt = (
                    pledge.pledge_subtotal
                    or (getattr(pledge, "pledge_qty", 1.0) * getattr(pledge, "pledge_amount_unit", 0.0))
                    or getattr(pledge, "pledge_amount", 0.0)
                    or 0.0
                )
                branch_data[cfg_id]["rahen_out"] += amt

        # 2. pos.pledge (Standard pledge model fallback)
        if "pos.pledge" in self.env:
            pledges_std_in = self.env["pos.pledge"].sudo().search([
                ("create_date", ">=", str_start),
                ("create_date", "<=", str_end),
                ("state", "in", ("active", "returned")),
            ])
            for pledge in pledges_std_in:
                cfg_id = pledge.pos_config_id.id if pledge.pos_config_id else (pledge.pos_order_id.config_id.id if pledge.pos_order_id else False)
                if not cfg_id or cfg_id not in active_config_ids:
                    continue
                branch_data[cfg_id]["rahen_in"] += pledge.pledge_amount or 0.0

            pledges_std_out = self.env["pos.pledge"].sudo().search([
                ("state", "=", "returned"),
                "|",
                "&", ("return_date", ">=", str_start), ("return_date", "<=", str_end),
                "&", ("return_date", "=", False),
                     "&", ("write_date", ">=", str_start), ("write_date", "<=", str_end),
            ])
            for pledge in pledges_std_out:
                cfg_id = pledge.pos_config_id.id if pledge.pos_config_id else (pledge.pos_order_id.config_id.id if pledge.pos_order_id else False)
                if not cfg_id or cfg_id not in active_config_ids:
                    continue
                branch_data[cfg_id]["rahen_out"] += pledge.pledge_amount or 0.0

        # Compute net pledges
        for cfg_id in active_config_ids:
            branch_data[cfg_id]["net_pledges"] = (
                branch_data[cfg_id]["rahen_in"] - branch_data[cfg_id]["rahen_out"]
            )

        # --- E. Collect Advance Orders & Deposits ---
        if "pos.advance.order" in self.env:
            adv_orders = self.env["pos.advance.order"].sudo().search([
                ("state", "not in", ("draft", "cancel")),
                "|",
                "&", ("create_date", ">=", str_start), ("create_date", "<=", str_end),
                "&", ("picking_date", ">=", str_start), ("picking_date", "<=", str_end),
            ])
            for adv in adv_orders:
                orig_cfg_id = adv.from_pos_config_id.id if adv.from_pos_config_id else (adv.pos_config_id.id if adv.pos_config_id else False)
                pick_cfg_id = adv.pos_config_id.id if adv.pos_config_id else orig_cfg_id

                dep_amt = adv.advance_amount or 0.0
                tot_amt = adv.amount_grand_total or adv.amount_total or 0.0
                rem_amt = adv.amount_remaining or 0.0

                if adv.create_date and dt_start <= adv.create_date <= dt_end:
                    if orig_cfg_id and orig_cfg_id in active_config_ids:
                        branch_data[orig_cfg_id]["advance_deposits"] += dep_amt
                        branch_data[orig_cfg_id]["advance_order_count"] += 1
                        branch_data[orig_cfg_id]["advance_order_total"] += tot_amt

                if adv.picking_date and dt_start <= adv.picking_date <= dt_end:
                    if pick_cfg_id and pick_cfg_id in active_config_ids:
                        branch_data[pick_cfg_id]["advance_pickup_value"] += tot_amt
                        branch_data[pick_cfg_id]["advance_remaining_amount"] += rem_amt
                        if adv.state in ("confirmed", "advance_paid"):
                            branch_data[pick_cfg_id]["advance_pending_count"] += 1

        # --- F. Format Per-Branch Rows & Calculate Global Totals ---
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

        # --- G. Build Channel Distribution & Daily Trends ---
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
        channels_filtered = [c for c in channels if c["value"] > 0]

        # Daily Trend calculation (group by day)
        trend_days = []
        curr_date = dt_start.date()
        while curr_date <= dt_end.date():
            day_str_start = fields.Datetime.to_string(datetime.combine(curr_date, time.min))
            day_str_end = fields.Datetime.to_string(datetime.combine(curr_date, time.max))

            day_payments = self.env["pos.payment"].sudo().search([
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

        # All branches list for tab navigation (sudo to ensure all active configs return)
        all_configs = self.env["pos.config"].sudo().search([("active", "=", True)], order="name")
        all_branches_list = [{"id": cfg.id, "name": cfg.name} for cfg in all_configs]

        return {
            "date_from": str_start,
            "date_to": str_end,
            "active_branches_count": len(configs),
            "all_branches": all_branches_list,
            "kpis": {
                "total_sales": global_totals["sales"],
                "untaxed_sales": global_totals["untaxed_sales"],
                "tax_amount": global_totals["tax_amount"],
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
                "advance_order_count": global_totals["advance_order_count"],
                "advance_order_total": global_totals["advance_order_total"],
                "advance_pickup_value": global_totals["advance_pickup_value"],
                "advance_remaining_amount": global_totals["advance_remaining_amount"],
                "advance_pending_count": global_totals["advance_pending_count"],
                "delivery_amount": global_totals["delivery_amount"],
                "order_count": global_totals["order_count"],
            },
            "branches": branch_rows,
            "global_totals": global_totals,
            "channels": channels_filtered,
            "trends": trend_days,
        }
