# -*- coding: utf-8 -*-
import logging
from collections import defaultdict
from datetime import datetime, time, timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class PosReportingDashboard(models.TransientModel):
    _name = "pos.reporting.dashboard"
    _description = "POS Executive Reporting & Dashboard Service"

    def _parse_datetime_bounds(self, date_from, date_to):
        """
        Parse date/datetime parameters into exact store shift datetime bounds.
        Default shift window: 06:00 AM on start day to 05:00 AM on following day.
        """
        today = fields.Date.context_today(self)

        def _to_dt(val, is_end=False):
            if not val:
                d = today
                if is_end:
                    tomorrow = d + timedelta(days=1)
                    return datetime.combine(tomorrow, time(5, 0, 0))
                return datetime.combine(d, time(6, 0, 0))
            if isinstance(val, datetime):
                return val

            val_str = str(val).strip().replace("T", " ")
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    return datetime.strptime(val_str.split(".")[0], fmt)
                except Exception:
                    pass
            try:
                d = fields.Date.from_string(val_str[:10])
                if d:
                    if is_end:
                        tomorrow = d + timedelta(days=1)
                        return datetime.combine(tomorrow, time(5, 0, 0))
                    return datetime.combine(d, time(6, 0, 0))
            except Exception:
                pass

            if is_end:
                tomorrow = today + timedelta(days=1)
                return datetime.combine(tomorrow, time(5, 0, 0))
            return datetime.combine(today, time(6, 0, 0))

        dt_start = _to_dt(date_from, is_end=False)
        dt_end = _to_dt(date_to, is_end=True)
        return dt_start, dt_end

    @api.model
    def get_dashboard_data(self, date_from=None, date_to=None, config_ids=None):
        """
        Fetch executive POS metrics across branch configurations for active multi-company context.
        Includes channel breakdowns, cash moves, pledges, advance orders, and orders per minute (OPM).
        """
        dt_start, dt_end = self._parse_datetime_bounds(date_from, date_to)
        str_start = fields.Datetime.to_string(dt_start)
        str_end = fields.Datetime.to_string(dt_end)

        # Operational duration in minutes for OPM calculations
        total_seconds = max((dt_end - dt_start).total_seconds(), 60.0)
        total_minutes = max(total_seconds / 60.0, 1.0)

        # Identify target POS configurations filtered by active companies
        config_domain = [
            ("active", "=", True),
            ("company_id", "in", self.env.companies.ids),
        ]
        if config_ids and isinstance(config_ids, (list, tuple)) and len(config_ids) > 0:
            config_domain.append(("id", "in", config_ids))

        configs = self.env["pos.config"].sudo().search(config_domain, order="name")
        active_config_ids = set(configs.ids)

        def _empty_branch_dict():
            return {
                "sales": 0.0,
                "untaxed_sales": 0.0,
                "tax_amount": 0.0,
                "discount_amount": 0.0,
                "cash": 0.0,
                "visa": 0.0,
                "online_sales": 0.0,
                "employee_debt": 0.0,
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
                "orders_per_min": 0.0,
            }

        branch_data = defaultdict(_empty_branch_dict)

        # Helper for classification
        def _classify_pm(pm):
            daily_type = getattr(pm, "daily_ops_report_type", "") or ""
            pm_type = getattr(pm, "type", "") or ""
            pm_name = (pm.name or "").lower()

            is_emp = "ذمم" in pm_name or "موظف" in pm_name or "employee" in pm_name or "ذمة" in pm_name or "ذمه" in pm_name or daily_type == "employee_debt"
            is_hosp = daily_type == "hospitality" or "hospitality" in pm_name or "ضيافة" in pm_name
            
            online_kw = ("talabat", "careem", "mythings", "kabseh", "طلبات", "كريم", "أشياتي", "توصيل", "delivery", "online")
            is_online = any(k in pm_name for k in online_kw) or daily_type in ("talabat", "careem", "mythings", "kabseh", "online")

            is_cash = not (is_emp or is_hosp or is_online) and (
                daily_type == "cash" or pm_type == "cash" or "cash" in pm_name or "نقد" in pm_name or "صندوق" in pm_name
            )

            is_visa = not (is_emp or is_hosp or is_online or is_cash) and (
                daily_type == "visa" or pm_type in ("bank", "pay_later") or "visa" in pm_name or "بطاقة" in pm_name or "card" in pm_name
            )

            return is_emp, is_hosp, is_online, is_cash, is_visa, pm_name

        # --- A. Collect POS Payments & Channel Breakdown ---
        payments = self.env["pos.payment"].sudo().search([
            ("pos_order_id.state", "in", ("paid", "done", "invoiced")),
            "|",
            "&", ("payment_date", ">=", str_start), ("payment_date", "<=", str_end),
            "&", ("payment_date", "=", False),
                 "&", ("pos_order_id.date_order", ">=", str_start), ("pos_order_id.date_order", "<=", str_end),
        ])

        # Group payments by POS Order to rebalance non-cash change adjustments
        order_payments = defaultdict(list)
        session_only_payments = []

        for pay in payments:
            if pay.pos_order_id:
                order_payments[pay.pos_order_id].append(pay)
            else:
                session_only_payments.append(pay)

        # Process session-only payments
        for pay in session_only_payments:
            cfg = pay.session_id.config_id if pay.session_id else False
            if not cfg or (active_config_ids and cfg.id not in active_config_ids):
                continue
            cfg_id = cfg.id
            amt = pay.amount or 0.0
            branch_data[cfg_id]["sales"] += amt
            is_emp, is_hosp, is_online, is_cash, is_visa, pm_name = _classify_pm(pay.payment_method_id)

            if is_emp:
                branch_data[cfg_id]["employee_debt"] += amt
            elif is_hosp:
                branch_data[cfg_id]["hospitality"] += amt
            elif is_online:
                branch_data[cfg_id]["online_sales"] += amt
            elif is_cash:
                branch_data[cfg_id]["cash"] += amt
            elif is_visa:
                branch_data[cfg_id]["visa"] += amt
            else:
                branch_data[cfg_id]["other_sales"] += amt

            if "talabat" in pm_name:
                branch_data[cfg_id]["talabat"] += amt
            elif "careem" in pm_name:
                branch_data[cfg_id]["careem"] += amt
            elif "mythings" in pm_name:
                branch_data[cfg_id]["mythings"] += amt
            elif "kabseh" in pm_name:
                branch_data[cfg_id]["kabseh"] += amt

        # Process order payments with cross-method change rebalancing
        for order, pay_list in order_payments.items():
            cfg = order.config_id
            if not cfg or (active_config_ids and cfg.id not in active_config_ids):
                continue
            cfg_id = cfg.id

            cat_amounts = defaultdict(float)
            pm_names = {}

            for pay in pay_list:
                amt = pay.amount or 0.0
                pm = pay.payment_method_id
                is_emp, is_hosp, is_online, is_cash, is_visa, pm_name = _classify_pm(pm)
                pm_names[pay.id] = pm_name

                if is_emp:
                    cat_amounts["employee_debt"] += amt
                elif is_hosp:
                    cat_amounts["hospitality"] += amt
                elif is_online:
                    cat_amounts["online_sales"] += amt
                elif is_cash:
                    cat_amounts["cash"] += amt
                elif is_visa:
                    cat_amounts["visa"] += amt
                else:
                    cat_amounts["other_sales"] += amt

                if "talabat" in pm_name:
                    branch_data[cfg_id]["talabat"] += amt
                elif "careem" in pm_name:
                    branch_data[cfg_id]["careem"] += amt
                elif "mythings" in pm_name:
                    branch_data[cfg_id]["mythings"] += amt
                elif "kabseh" in pm_name:
                    branch_data[cfg_id]["kabseh"] += amt

            # If cash is negative (change given) but non-cash methods cover the order total
            non_cash_sum = cat_amounts["visa"] + cat_amounts["online_sales"] + cat_amounts["employee_debt"] + cat_amounts["hospitality"] + cat_amounts["other_sales"]
            if cat_amounts["cash"] < 0 and non_cash_sum > 0:
                ord_tot = order.amount_total or 0.0
                if ord_tot >= 0:
                    excess = max(0.0, non_cash_sum - ord_tot)
                    if excess > 0:
                        # Rebalance: cap non-cash to actual order total and remove negative cash drag
                        scale = ord_tot / non_cash_sum if non_cash_sum > 0 else 1.0
                        cat_amounts["visa"] *= scale
                        cat_amounts["online_sales"] *= scale
                        cat_amounts["employee_debt"] *= scale
                        cat_amounts["hospitality"] *= scale
                        cat_amounts["other_sales"] *= scale
                        cat_amounts["cash"] = max(0.0, cat_amounts["cash"] + excess)

            order_sales = sum(cat_amounts.values())
            branch_data[cfg_id]["sales"] += order_sales
            branch_data[cfg_id]["cash"] += cat_amounts["cash"]
            branch_data[cfg_id]["visa"] += cat_amounts["visa"]
            branch_data[cfg_id]["online_sales"] += cat_amounts["online_sales"]
            branch_data[cfg_id]["employee_debt"] += cat_amounts["employee_debt"]
            branch_data[cfg_id]["hospitality"] += cat_amounts["hospitality"]
            branch_data[cfg_id]["other_sales"] += cat_amounts["other_sales"]

        # --- B. Collect POS Orders ---
        pos_orders = self.env["pos.order"].sudo().search([
            ("state", "in", ("paid", "done", "invoiced")),
            ("date_order", ">=", str_start),
            ("date_order", "<=", str_end),
        ])
        for order in pos_orders:
            cfg = order.config_id
            if not cfg or (active_config_ids and cfg.id not in active_config_ids):
                continue
            cfg_id = cfg.id

            tax_amt = getattr(order, "amount_tax", 0.0) or 0.0
            tot_amt = getattr(order, "amount_total", 0.0) or 0.0
            untaxed_amt = getattr(order, "amount_untaxed", None)
            if untaxed_amt is None:
                untaxed_amt = tot_amt - tax_amt

            order_disc = sum(
                (line.price_unit or 0.0) * (line.qty or 0.0) * (line.discount / 100.0)
                for line in order.lines if line.discount
            )

            branch_data[cfg_id]["untaxed_sales"] += untaxed_amt
            branch_data[cfg_id]["tax_amount"] += tax_amt
            branch_data[cfg_id]["discount_amount"] += order_disc
            branch_data[cfg_id]["delivery_amount"] += getattr(order, "delivery_amount", 0.0) or 0.0
            branch_data[cfg_id]["order_count"] += 1

        # --- C. Collect Cash In / Out Moves ---
        st_lines = self.env["account.bank.statement.line"].sudo().search([
            ("date", ">=", dt_start.date()),
            ("date", "<=", dt_end.date() + timedelta(days=1)),
        ])
        for st in st_lines:
            cfg = st.pos_session_id.config_id if st.pos_session_id else False
            if not cfg or (active_config_ids and cfg.id not in active_config_ids):
                continue
            cfg_id = cfg.id

            st_dt = st.create_date or (datetime.combine(st.date, time.min) if st.date else False)
            if st_dt and not (dt_start <= st_dt <= dt_end):
                continue

            amt = st.amount or 0.0
            if amt > 0:
                branch_data[cfg_id]["cash_in"] += amt
            else:
                branch_data[cfg_id]["cash_out"] += abs(amt)

        for cfg_id in active_config_ids:
            branch_data[cfg_id]["net_cash_moves"] = (
                branch_data[cfg_id]["cash_in"] - branch_data[cfg_id]["cash_out"]
            )
            branch_data[cfg_id]["orders_per_min"] = round(
                branch_data[cfg_id]["order_count"] / total_minutes, 2
            )

        # --- D. Collect Pledges (Filtered by Date Range) ---
        if "pos.advance.order.pledge" in self.env:
            pledge_recs = self.env["pos.advance.order.pledge"].sudo().search([
                "|",
                "&", ("receive_date", ">=", str_start), ("receive_date", "<=", str_end),
                "&", ("create_date", ">=", str_start), ("create_date", "<=", str_end),
            ])
            for pledge in pledge_recs:
                cfg_id = False
                if pledge.pos_order_id:
                    cfg_id = pledge.pos_order_id.config_id.id
                elif pledge.order_id and hasattr(pledge.order_id, "pos_config_id"):
                    cfg_id = pledge.order_id.pos_config_id.id
                elif pledge.order_id and hasattr(pledge.order_id, "from_pos_config_id"):
                    cfg_id = pledge.order_id.from_pos_config_id.id

                if not cfg_id or (active_config_ids and cfg_id not in active_config_ids):
                    continue

                amt = (
                    pledge.pledge_subtotal
                    or (getattr(pledge, "pledge_qty", 1.0) * getattr(pledge, "pledge_amount_unit", 0.0))
                    or getattr(pledge, "pledge_amount", 0.0)
                    or 0.0
                )

                rec_dt = pledge.receive_date or pledge.create_date
                ret_dt = pledge.return_date or (pledge.write_date if pledge.state == "returned" else None)

                if rec_dt and dt_start <= rec_dt <= dt_end:
                    branch_data[cfg_id]["rahen_in"] += amt

                if pledge.state == "returned" and ret_dt and dt_start <= ret_dt <= dt_end:
                    branch_data[cfg_id]["rahen_out"] += amt

        if "pos.pledge" in self.env:
            pledges_std = self.env["pos.pledge"].sudo().search([
                ("create_date", ">=", str_start),
                ("create_date", "<=", str_end),
            ])
            for pledge in pledges_std:
                cfg_id = pledge.pos_config_id.id if pledge.pos_config_id else (pledge.pos_order_id.config_id.id if pledge.pos_order_id else False)
                if not cfg_id or (active_config_ids and cfg_id not in active_config_ids):
                    continue

                amt = pledge.pledge_amount or 0.0
                c_dt = pledge.create_date
                r_dt = pledge.return_date or (pledge.write_date if pledge.state == "returned" else None)

                if c_dt and dt_start <= c_dt <= dt_end:
                    branch_data[cfg_id]["rahen_in"] += amt

                if pledge.state == "returned" and r_dt and dt_start <= r_dt <= dt_end:
                    branch_data[cfg_id]["rahen_out"] += amt

        for cfg_id in active_config_ids:
            branch_data[cfg_id]["net_pledges"] = (
                branch_data[cfg_id]["rahen_in"] - branch_data[cfg_id]["rahen_out"]
            )

        # --- E. Collect Advance Orders ---
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
                    if orig_cfg_id and (not active_config_ids or orig_cfg_id in active_config_ids):
                        branch_data[orig_cfg_id]["advance_deposits"] += dep_amt
                        branch_data[orig_cfg_id]["advance_order_count"] += 1
                        branch_data[orig_cfg_id]["advance_order_total"] += tot_amt

                if adv.picking_date and dt_start <= adv.picking_date <= dt_end:
                    if pick_cfg_id and (not active_config_ids or pick_cfg_id in active_config_ids):
                        branch_data[pick_cfg_id]["advance_pickup_value"] += tot_amt
                        branch_data[pick_cfg_id]["advance_remaining_amount"] += rem_amt
                        if adv.state in ("confirmed", "advance_paid"):
                            branch_data[pick_cfg_id]["advance_pending_count"] += 1

        # --- F. Build Rows & Global Totals ---
        branch_rows = []
        global_totals = _empty_branch_dict()

        for config in configs:
            vals = branch_data[config.id]
            row = {"config_id": config.id, "branch_name": config.name, **vals}
            branch_rows.append(row)

            for key in global_totals.keys():
                global_totals[key] += vals[key]

        global_totals["orders_per_min"] = round(global_totals["order_count"] / total_minutes, 2)

        # --- G. Build Channel Distribution & Daily Trends ---
        channels = [
            {"name": _("Cash Sales"), "value": global_totals["cash"], "color": "#28a745"},
            {"name": _("Visa / Card"), "value": global_totals["visa"], "color": "#007bff"},
            {"name": _("Online & Delivery"), "value": global_totals["online_sales"], "color": "#fd7e14"},
            {"name": _("Debt Sales (مبيعات الذمم)"), "value": global_totals["employee_debt"], "color": "#6f42c1"},
            {"name": _("Hospitality"), "value": global_totals["hospitality"], "color": "#ffc107"},
            {"name": _("Talabat"), "value": global_totals["talabat"], "color": "#fd7e14"},
            {"name": _("Careem"), "value": global_totals["careem"], "color": "#20c997"},
            {"name": _("Mythings"), "value": global_totals["mythings"], "color": "#17a2b8"},
            {"name": _("Kabseh"), "value": global_totals["kabseh"], "color": "#e83e8c"},
            {"name": _("Other Channels"), "value": global_totals["other_sales"], "color": "#6c757d"},
        ]
        channels_filtered = [c for c in channels if c["value"] > 0]

        # Batched daily trend evaluation
        all_trend_payments = payments

        trend_days = []
        curr_date = dt_start.date()
        while curr_date <= dt_end.date():
            day_dt_start = datetime.combine(curr_date, time(6, 0, 0))
            day_dt_end = datetime.combine(curr_date + timedelta(days=1), time(5, 0, 0))

            day_total = 0.0
            day_cash = 0.0

            for p in all_trend_payments:
                cfg = p.session_id.config_id if p.session_id else (p.pos_order_id.config_id if p.pos_order_id else False)
                if active_config_ids and (not cfg or cfg.id not in active_config_ids):
                    continue

                p_date = p.payment_date or (p.pos_order_id.date_order if p.pos_order_id else False)
                if not p_date or not (day_dt_start <= p_date <= day_dt_end):
                    continue

                amt = p.amount or 0.0
                day_total += amt

                is_emp, is_hosp, is_online, is_cash, is_visa, pm_name = _classify_pm(p.payment_method_id)
                if is_cash:
                    day_cash += amt

            day_visa = day_total - day_cash

            trend_days.append({
                "date": curr_date.strftime("%Y-%m-%d"),
                "date_label": curr_date.strftime("%b %d"),
                "total_sales": day_total,
                "cash_sales": day_cash,
                "visa_sales": day_visa,
            })
            curr_date += timedelta(days=1)

        all_configs = self.env["pos.config"].sudo().search([
            ("active", "=", True),
            ("company_id", "in", self.env.companies.ids),
        ], order="name")
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
                "discount_amount": global_totals["discount_amount"],
                "cash_sales": global_totals["cash"],
                "visa_sales": global_totals["visa"],
                "online_sales": global_totals["online_sales"],
                "employee_debt": global_totals["employee_debt"],
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
                "orders_per_min": global_totals["orders_per_min"],
            },
            "branches": branch_rows,
            "global_totals": global_totals,
            "channels": channels_filtered,
            "trends": trend_days,
        }

    @api.model
    def open_kpi_drilldown(self, metric_type, date_from=None, date_to=None, config_ids=None):
        """
        Populate transient records in pos.unified.report for metric_type and return drill-down action.
        Scoped to the active user to prevent concurrent transient data collisions.
        """
        dt_start, dt_end = self._parse_datetime_bounds(date_from, date_to)
        str_start = fields.Datetime.to_string(dt_start)
        str_end = fields.Datetime.to_string(dt_end)

        config_domain = [
            ("active", "=", True),
            ("company_id", "in", self.env.companies.ids),
        ]
        if config_ids and isinstance(config_ids, (list, tuple)) and len(config_ids) > 0:
            config_domain.append(("id", "in", config_ids))

        configs = self.env["pos.config"].sudo().search(config_domain)
        active_config_ids = set(configs.ids)

        # Clear previous transient drill-down records for current user
        self.env["pos.unified.report"].sudo().search([("create_uid", "=", self.env.user.id)]).unlink()

        vals_list = []

        # Classification helper
        def _classify_pm(pm):
            daily_type = getattr(pm, "daily_ops_report_type", "") or ""
            pm_type = getattr(pm, "type", "") or ""
            pm_name = (pm.name or "").lower()

            is_emp = "ذمم" in pm_name or "موظف" in pm_name or "employee" in pm_name or "ذمة" in pm_name or "ذمه" in pm_name or daily_type == "employee_debt"
            is_hosp = daily_type == "hospitality" or "hospitality" in pm_name or "ضيافة" in pm_name

            online_kw = ("talabat", "careem", "mythings", "kabseh", "طلبات", "كريم", "أشياتي", "توصيل", "delivery", "online")
            is_online = any(k in pm_name for k in online_kw) or daily_type in ("talabat", "careem", "mythings", "kabseh", "online")

            is_cash = not (is_emp or is_hosp or is_online) and (
                daily_type == "cash" or pm_type == "cash" or "cash" in pm_name or "نقد" in pm_name or "صندوق" in pm_name
            )

            is_visa = not (is_emp or is_hosp or is_online or is_cash) and (
                daily_type == "visa" or pm_type in ("bank", "pay_later") or "visa" in pm_name or "بطاقة" in pm_name or "card" in pm_name
            )

            return is_emp, is_hosp, is_online, is_cash, is_visa

        if metric_type in ("sales", "cash_sales", "visa_sales", "employee_debt", "online_sales"):
            payments = self.env["pos.payment"].sudo().search([
                ("pos_order_id.state", "in", ("paid", "done", "invoiced")),
                "|",
                "&", ("payment_date", ">=", str_start), ("payment_date", "<=", str_end),
                "&", ("payment_date", "=", False),
                     "&", ("pos_order_id.date_order", ">=", str_start), ("pos_order_id.date_order", "<=", str_end),
            ])
            for pay in payments:
                cfg = pay.session_id.config_id if pay.session_id else (pay.pos_order_id.config_id if pay.pos_order_id else False)
                if not cfg or cfg.id not in active_config_ids:
                    continue

                pm = pay.payment_method_id
                is_emp, is_hosp, is_online, is_cash, is_visa = _classify_pm(pm)

                include = False
                if metric_type == "sales":
                    include = True
                elif metric_type == "employee_debt" and is_emp:
                    include = True
                elif metric_type == "online_sales" and is_online:
                    include = True
                elif metric_type == "cash_sales" and is_cash:
                    include = True
                elif metric_type == "visa_sales" and is_visa:
                    include = True

                if include:
                    amt = pay.amount or 0.0
                    po = pay.pos_order_id
                    tax_amt_full = getattr(po, "amount_tax", 0.0) or 0.0 if po else 0.0
                    tot_amt_full = getattr(po, "amount_total", 0.0) or 0.0 if po else amt
                    untaxed_amt_full = getattr(po, "amount_untaxed", None) if po else None
                    if untaxed_amt_full is None:
                        untaxed_amt_full = tot_amt_full - tax_amt_full
                    order_disc_full = sum(
                        (l.price_unit or 0.0) * (l.qty or 0.0) * (l.discount / 100.0)
                        for l in po.lines if l.discount
                    ) if po else 0.0

                    # Proportional Untaxed & Tax allocation per payment line to prevent deduplication errors
                    ratio = (amt / tot_amt_full) if (tot_amt_full and tot_amt_full != 0.0) else 1.0
                    untaxed_amt = untaxed_amt_full * ratio
                    tax_amt = tax_amt_full * ratio
                    order_disc = order_disc_full * ratio

                    vals_list.append({
                        "name": po.name if po else (pay.name or _("POS Payment")),
                        "date": pay.payment_date or (po.date_order if po else dt_start),
                        "config_id": cfg.id,
                        "session_id": pay.session_id.id if pay.session_id else False,
                        "payment_method_id": pm.id,
                        "pos_order_id": po.id if po else False,
                        "report_type": "online_sales" if is_online else "pos_sales",
                        "amount": amt,
                        "untaxed_amount": untaxed_amt,
                        "tax_amount": tax_amt,
                        "discount_amount": order_disc,
                        "employee_debt_amount": amt if is_emp else 0.0,
                        "cash_amount": amt if is_cash else 0.0,
                        "visa_amount": amt if is_visa else 0.0,
                        "partner_id": po.partner_id.id if po else False,
                        "company_id": cfg.company_id.id,
                    })          "company_id": cfg.company_id.id,
                    })

        elif metric_type in ("untaxed_sales", "tax_amount", "discount_amount"):
            pos_orders = self.env["pos.order"].sudo().search([
                ("state", "in", ("paid", "done", "invoiced")),
                ("date_order", ">=", str_start),
                ("date_order", "<=", str_end),
            ])
            for order in pos_orders:
                cfg = order.config_id
                if not cfg or cfg.id not in active_config_ids:
                    continue

                tax_amt = getattr(order, "amount_tax", 0.0) or 0.0
                tot_amt = getattr(order, "amount_total", 0.0) or 0.0
                untaxed_amt = getattr(order, "amount_untaxed", None)
                if untaxed_amt is None:
                    untaxed_amt = tot_amt - tax_amt

                order_disc = sum(
                    (line.price_unit or 0.0) * (line.qty or 0.0) * (line.discount / 100.0)
                    for line in order.lines if line.discount
                )

                amt = 0.0
                if metric_type == "untaxed_sales":
                    amt = untaxed_amt
                elif metric_type == "tax_amount":
                    amt = tax_amt
                elif metric_type == "discount_amount":
                    amt = order_disc

                if amt != 0.0:
                    vals_list.append({
                        "name": order.name or _("POS Order"),
                        "date": order.date_order,
                        "config_id": cfg.id,
                        "session_id": order.session_id.id if order.session_id else False,
                        "pos_order_id": order.id,
                        "report_type": "pos_sales",
                        "amount": tot_amt,
                        "untaxed_amount": untaxed_amt,
                        "tax_amount": tax_amt,
                        "discount_amount": order_disc,
                        "partner_id": order.partner_id.id if order.partner_id else False,
                        "company_id": cfg.company_id.id,
                    })

        elif metric_type == "net_cash_moves":
            st_lines = self.env["account.bank.statement.line"].sudo().search([
                ("date", ">=", dt_start.date()),
                ("date", "<=", dt_end.date() + timedelta(days=1)),
            ])
            for st in st_lines:
                cfg = st.pos_session_id.config_id if st.pos_session_id else False
                if not cfg or cfg.id not in active_config_ids:
                    continue

                st_dt = st.create_date or (datetime.combine(st.date, time.min) if st.date else False)
                if st_dt and not (dt_start <= st_dt <= dt_end):
                    continue

                amt = st.amount or 0.0
                is_in = amt > 0
                vals_list.append({
                    "name": st.payment_ref or st.ref or st.name or _("Cash Move"),
                    "date": st_dt or str_start,
                    "config_id": cfg.id,
                    "session_id": st.pos_session_id.id if st.pos_session_id else False,
                    "report_type": "cash_in" if is_in else "cash_out",
                    "amount": abs(amt),
                    "cash_in_amount": amt if is_in else 0.0,
                    "cash_out_amount": abs(amt) if not is_in else 0.0,
                    "partner_id": st.partner_id.id if st.partner_id else False,
                    "company_id": cfg.company_id.id,
                })

        elif metric_type == "net_pledges":
            if "pos.advance.order.pledge" in self.env:
                pledge_recs = self.env["pos.advance.order.pledge"].sudo().search([
                    "|",
                    "&", ("receive_date", ">=", str_start), ("receive_date", "<=", str_end),
                    "&", ("create_date", ">=", str_start), ("create_date", "<=", str_end),
                ])
                for pledge in pledge_recs:
                    cfg = pledge.pos_order_id.config_id if pledge.pos_order_id else (
                        pledge.order_id.pos_config_id if (pledge.order_id and hasattr(pledge.order_id, "pos_config_id")) else (
                            pledge.order_id.from_pos_config_id if (pledge.order_id and hasattr(pledge.order_id, "from_pos_config_id")) else False
                        )
                    )
                    if not cfg or cfg.id not in active_config_ids:
                        continue

                    amt = pledge.pledge_subtotal or (getattr(pledge, "pledge_qty", 1.0) * getattr(pledge, "pledge_amount_unit", 0.0)) or 0.0
                    rec_dt = pledge.receive_date or pledge.create_date
                    ret_dt = pledge.return_date or (pledge.write_date if pledge.state == "returned" else None)

                    if rec_dt and dt_start <= rec_dt <= dt_end:
                        vals_list.append({
                            "name": _("Pledge Received: %s") % (pledge.display_name or pledge.product_id.name),
                            "date": rec_dt,
                            "config_id": cfg.id,
                            "report_type": "rahen_in",
                            "amount": amt,
                            "rahen_in_amount": amt,
                            "partner_id": pledge.partner_id.id if hasattr(pledge, "partner_id") else False,
                            "company_id": cfg.company_id.id,
                        })

                    if pledge.state == "returned" and ret_dt and dt_start <= ret_dt <= dt_end:
                        vals_list.append({
                            "name": _("Pledge Returned: %s") % (pledge.display_name or pledge.product_id.name),
                            "date": ret_dt,
                            "config_id": cfg.id,
                            "report_type": "rahen_out",
                            "amount": amt,
                            "rahen_out_amount": amt,
                            "partner_id": pledge.partner_id.id if hasattr(pledge, "partner_id") else False,
                            "company_id": cfg.company_id.id,
                        })

        elif metric_type == "advance_deposits":
            if "pos.advance.order" in self.env:
                adv_orders = self.env["pos.advance.order"].sudo().search([
                    ("state", "not in", ("draft", "cancel")),
                    ("create_date", ">=", str_start),
                    ("create_date", "<=", str_end),
                ])
                for adv in adv_orders:
                    cfg = adv.from_pos_config_id if adv.from_pos_config_id else adv.pos_config_id
                    if not cfg or cfg.id not in active_config_ids:
                        continue

                    c_dt = adv.create_date
                    if c_dt and dt_start <= c_dt <= dt_end:
                        amt = adv.advance_amount or 0.0
                        vals_list.append({
                            "name": adv.name or _("Advance Order Deposit"),
                            "date": c_dt,
                            "config_id": cfg.id,
                            "report_type": "advance_deposit",
                            "amount": amt,
                            "advance_amount": amt,
                            "partner_id": adv.partner_id.id if hasattr(adv, "partner_id") else False,
                            "company_id": cfg.company_id.id,
                        })

        if vals_list:
            self.env["pos.unified.report"].sudo().create(vals_list)

        wizard_vals = {"date_from": dt_start, "date_to": dt_end}
        if config_ids:
            wizard_vals["config_ids"] = [(6, 0, list(config_ids))]
        wiz = self.env["pos.unified.report.wizard"].sudo().create(wizard_vals)

        metric_titles = {
            "sales": _("Gross Sales Transactions"),
            "untaxed_sales": _("Sales Without Tax Transactions"),
            "tax_amount": _("Sales Tax Transactions"),
            "discount_amount": _("Order Discount Transactions"),
            "cash_sales": _("Cash Sales Transactions"),
            "visa_sales": _("Visa & Card Sales Transactions"),
            "online_sales": _("Online & Delivery Sales Transactions"),
            "employee_debt": _("Debt Sales (مبيعات الذمم) Transactions"),
            "net_cash_moves": _("Cash Moves (In / Out) Transactions"),
            "net_pledges": _("Pledges (Rahen In / Out) Transactions"),
            "advance_deposits": _("Advance Order Deposit Transactions"),
        }
        title = metric_titles.get(metric_type, _("Metric Drill-Down Transactions"))

        return {
            "name": title,
            "type": "ir.actions.act_window",
            "res_model": "pos.unified.report",
            "view_mode": "list,pivot,graph",
            "views": [
                (self.env.ref("anabtawi_pos_reporting_dashboard.view_pos_unified_report_tree").id, "list"),
                (self.env.ref("anabtawi_pos_reporting_dashboard.view_pos_unified_report_pivot").id, "pivot"),
            ],
            "target": "current",
            "context": {
                "active_wizard_id": wiz.id,
                "metric_type": metric_type,
            },
        }

