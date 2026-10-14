# -*- coding: utf-8 -*-
import calendar
import logging
from collections import defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.addons.pos_ameen_daily_operation.models.pos_daily_ops_engine import DELIVERY_CHANNELS

_logger = logging.getLogger(__name__)

DASHBOARD_EXTRA_KEYS = {
    "untaxed_sales": 0.0,
    "tax_amount": 0.0,
    "discount_amount": 0.0,
    "net_cash_moves": 0.0,
    "net_pledges": 0.0,
    "pledge_cash_net": 0.0,
    "pledge_visa_net": 0.0,
    "advance_deposits": 0.0,
    "advance_cash": 0.0,
    "advance_visa": 0.0,
    "advance_cash_count": 0,
    "advance_visa_count": 0,
    "advance_order_count": 0,
    "advance_order_total": 0.0,
    "advance_pickup_value": 0.0,
    "advance_remaining_amount": 0.0,
    "advance_pending_count": 0,
    "order_count": 0,
    "orders_per_min": 0.0,
    "attendant_employee_count": 0,
    "total_labor_cost": 0.0,
}

PAYMENT_METRICS = ("sales", "cash_sales", "visa_sales", "employee_debt", "online_sales")


class PosReportingDashboard(models.TransientModel):
    _name = "pos.reporting.dashboard"
    _description = "POS Executive Reporting & Dashboard Service"

    def _parse_period(self, date_from, date_to):
        """Business-date period from 'YYYY-MM-DD' (or datetime) strings; defaults to today."""
        today = fields.Date.context_today(self)

        def _to_date(val):
            if not val:
                return today
            try:
                return fields.Date.to_date(str(val).strip()[:10])
            except ValueError:
                return today

        return self.env["pos.daily.ops.engine"]._get_period(_to_date(date_from), _to_date(date_to))

    def _get_report_configs(self, config_ids=None):
        domain = [
            ("active", "=", True),
            ("company_id", "in", self.env.companies.ids),
        ]
        if config_ids and isinstance(config_ids, (list, tuple)) and len(config_ids) > 0:
            domain.append(("id", "in", config_ids))
        return self.env["pos.config"].sudo().search(domain, order="name")

    def _get_pledge_movements(self, period, configs):
        return self.env["pos.daily.ops.engine"]._get_pledge_movements(period, configs)

    def _advance_channel(self, adv):
        """'cash' or 'visa' for an advance order deposit."""
        channel = self.env["pos.daily.ops.engine"]._get_channel(adv.pos_payment_method_id)
        if channel:
            return channel
        return "cash" if (adv.payment_method or "cash") == "cash" else "visa"

    def _get_advance_orders(self, period):
        start, end = period["business_start"], period["business_end"]
        return self.env["pos.advance.order"].sudo().search([
            ("state", "not in", ("draft", "cancel")),
            "|",
            "&", ("create_date", ">=", start), ("create_date", "<", end),
            "&", ("picking_date", ">=", start), ("picking_date", "<", end),
        ])

    def _get_attendances(self, period):
        if "hr.attendance" not in self.env:
            return []
        return self.env["hr.attendance"].sudo().search([
            ("check_in", ">=", period["business_start"]),
            ("check_in", "<", period["business_end"]),
        ])

    def _get_employee_pos_config(self, emp, configs):
        """Map an employee to a POS branch via department path, work location or company."""
        if hasattr(emp, "pos_config_id") and emp.pos_config_id:
            return emp.pos_config_id
        if hasattr(emp, "pos_config_ids") and emp.pos_config_ids:
            return emp.pos_config_ids[0]

        dept_full_path = ""
        leaf_dept_name = ""
        if emp.department_id:
            dept_full_path = (getattr(emp.department_id, "complete_name", None) or emp.department_id.name or "").strip()
            path_parts = [p.strip() for p in dept_full_path.split("/") if p.strip()]
            leaf_dept_name = path_parts[-1] if path_parts else ""

        loc_name = (emp.work_location_id.name or "").strip() if hasattr(emp, "work_location_id") and emp.work_location_id else ""

        clean_leaf = leaf_dept_name.lower()
        clean_full = dept_full_path.lower()
        clean_loc = loc_name.lower()

        # Tier 1: Exact match on leaf department name or work location
        if clean_leaf or clean_loc:
            for cfg in configs:
                cfg_name = (cfg.name or "").strip().lower()
                if (clean_leaf and cfg_name == clean_leaf) or (clean_loc and cfg_name == clean_loc):
                    return cfg

        # Tier 2: Leaf department name or work location is contained in POS config name (or vice versa)
        if clean_leaf or clean_loc:
            for cfg in configs:
                cfg_name = (cfg.name or "").strip().lower()
                if clean_leaf and (clean_leaf in cfg_name or cfg_name in clean_leaf):
                    return cfg
                if clean_loc and (clean_loc in cfg_name or cfg_name in clean_loc):
                    return cfg

        # Tier 3: POS config name is contained anywhere within the full department path
        if clean_full:
            for cfg in configs:
                cfg_name = (cfg.name or "").strip().lower()
                if cfg_name and cfg_name in clean_full:
                    return cfg

        # Tier 4: Single company POS config fallback
        company_cfgs = [c for c in configs if c.company_id.id == emp.company_id.id]
        if len(company_cfgs) == 1:
            return company_cfgs[0]
        return False

    @staticmethod
    def _employee_daily_cost(emp, att_date):
        num_days = calendar.monthrange(att_date.year, att_date.month)[1]
        wage = getattr(emp, "wage", 0.0) or (
            emp.contract_id.wage if (hasattr(emp, "contract_id") and emp.contract_id and emp.contract_id.wage) else 0.0
        ) or 0.0
        return wage / float(num_days) if num_days > 0 else 0.0

    @staticmethod
    def _order_discount(order):
        return sum(
            (line.price_unit or 0.0) * (line.qty or 0.0) * (line.discount / 100.0)
            for line in order.lines if line.discount
        )

    @staticmethod
    def _order_untaxed(order):
        untaxed = getattr(order, "amount_untaxed", None)
        if untaxed is None:
            untaxed = (order.amount_total or 0.0) - (order.amount_tax or 0.0)
        return untaxed

    def _payment_matches_metric(self, payment_method, metric_type):
        bucket = self.env["pos.daily.ops.engine"]._get_bucket(payment_method)
        if metric_type == "sales":
            return bucket != "hospitality"
        if metric_type == "cash_sales":
            return bucket == "cash"
        if metric_type == "visa_sales":
            return bucket == "visa"
        if metric_type == "employee_debt":
            return bucket == "employee_debt"
        if metric_type == "online_sales":
            return bucket in DELIVERY_CHANNELS
        return False

    @api.model
    def get_dashboard_data(self, date_from=None, date_to=None, config_ids=None):
        """
        Fetch executive POS metrics across branch configurations for active multi-company context.
        Sales, payment channels, cash moves and pledges come from the shared Daily Operations
        engine so they always match the Daily Operations Excel report.
        """
        engine = self.env["pos.daily.ops.engine"]
        period = self._parse_period(date_from, date_to)
        configs = self._get_report_configs(config_ids)
        active_config_ids = set(configs.ids)

        sessions = engine._get_sessions(period, configs)
        figures = engine._compute_branch_figures(period, configs, sessions=sessions)

        def _empty_branch_dict():
            return {**engine._empty_figures(), **DASHBOARD_EXTRA_KEYS}

        branch_data = defaultdict(_empty_branch_dict)
        for cfg_id, values in figures.items():
            branch_data[cfg_id].update(values)

        total_minutes = max((period["business_end"] - period["business_start"]).total_seconds() / 60.0, 1.0)

        # --- A. POS Orders of the period's sessions (tax, discounts, order count) ---
        for order in engine._get_orders(sessions):
            branch = branch_data[order.config_id.id]
            branch["untaxed_sales"] += self._order_untaxed(order)
            branch["tax_amount"] += order.amount_tax or 0.0
            branch["discount_amount"] += self._order_discount(order)
            branch["order_count"] += 1

        for cfg_id in active_config_ids:
            branch = branch_data[cfg_id]
            branch["net_cash_moves"] = branch["cash_in"] - branch["cash_out"]
            branch["net_pledges"] = branch["rahen_in"] - branch["rahen_out"]
            branch["pledge_cash_net"] = branch["pledge_cash_in"] - branch["pledge_cash_out"]
            branch["pledge_visa_net"] = branch["pledge_visa_in"] - branch["pledge_visa_out"]
            branch["orders_per_min"] = round(branch["order_count"] / total_minutes, 2)

        # --- B. Advance Orders ---
        for adv in self._get_advance_orders(period):
            orig_cfg_id = adv.from_pos_config_id.id or adv.pos_config_id.id
            pick_cfg_id = adv.pos_config_id.id or orig_cfg_id

            dep_amt = adv.advance_amount or 0.0
            tot_amt = adv.amount_grand_total or adv.amount_total or 0.0
            rem_amt = adv.amount_remaining or 0.0

            if engine._in_business_window(period, adv.create_date) and orig_cfg_id in active_config_ids:
                branch = branch_data[orig_cfg_id]
                branch["advance_deposits"] += dep_amt
                branch["advance_order_count"] += 1
                branch["advance_order_total"] += tot_amt
                channel = self._advance_channel(adv)
                branch["advance_%s" % channel] += dep_amt
                branch["advance_%s_count" % channel] += 1

            if engine._in_business_window(period, adv.picking_date) and pick_cfg_id in active_config_ids:
                branch = branch_data[pick_cfg_id]
                branch["advance_pickup_value"] += tot_amt
                branch["advance_remaining_amount"] += rem_amt
                if adv.state in ("confirmed", "advance_paid"):
                    branch["advance_pending_count"] += 1

        # --- C. Attendance & Daily Employee Labor Cost ---
        branch_daily_attendants = defaultdict(lambda: defaultdict(set))
        for att in self._get_attendances(period):
            emp = att.employee_id
            if not emp:
                continue
            cfg = self._get_employee_pos_config(emp, configs)
            if not cfg or cfg.id not in active_config_ids:
                continue
            branch_daily_attendants[cfg.id][att.check_in.date()].add(emp)

        for cfg_id, daily_map in branch_daily_attendants.items():
            all_attending_emp_ids = set()
            total_cost = 0.0
            for att_date, emp_set in daily_map.items():
                all_attending_emp_ids.update(e.id for e in emp_set)
                for emp in emp_set:
                    total_cost += self._employee_daily_cost(emp, att_date)
            branch_data[cfg_id]["attendant_employee_count"] = len(all_attending_emp_ids)
            branch_data[cfg_id]["total_labor_cost"] = round(total_cost, 3)

        # --- D. Build Rows & Global Totals ---
        branch_rows = []
        global_totals = _empty_branch_dict()
        for config in configs:
            vals = branch_data[config.id]
            branch_rows.append({"config_id": config.id, "branch_name": config.name, **vals})
            for key in global_totals:
                global_totals[key] += vals[key]

        global_totals["orders_per_min"] = round(global_totals["order_count"] / total_minutes, 2)

        # --- E. Channel Distribution ---
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

        # --- F. Daily Trends (by business date of the session) ---
        day_totals = defaultdict(lambda: {"total": 0.0, "cash": 0.0, "visa": 0.0})
        if sessions:
            groups = self.env["pos.payment"].sudo()._read_group(
                [("session_id", "in", sessions.ids)],
                ["session_id", "payment_method_id"],
                ["amount:sum"],
            )
            for session, payment_method, amount in groups:
                bucket = engine._get_bucket(payment_method)
                if bucket == "hospitality":
                    continue
                day = day_totals[engine._to_local_date(session.start_at)]
                day["total"] += amount or 0.0
                if bucket in ("cash", "visa"):
                    day[bucket] += amount or 0.0

        trend_days = []
        curr_date = period["date_from"]
        while curr_date <= period["date_to"]:
            day = day_totals[curr_date]
            trend_days.append({
                "date": curr_date.strftime("%Y-%m-%d"),
                "date_label": curr_date.strftime("%b %d"),
                "total_sales": day["total"],
                "cash_sales": day["cash"],
                "visa_sales": day["visa"],
            })
            curr_date += timedelta(days=1)

        all_configs = self._get_report_configs()
        all_branches_list = [{"id": cfg.id, "name": cfg.name} for cfg in all_configs]

        return {
            "date_from": fields.Date.to_string(period["date_from"]),
            "date_to": fields.Date.to_string(period["date_to"]),
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
                "pledge_cash_in": global_totals["pledge_cash_in"],
                "pledge_cash_out": global_totals["pledge_cash_out"],
                "pledge_cash_net": global_totals["pledge_cash_net"],
                "pledge_visa_in": global_totals["pledge_visa_in"],
                "pledge_visa_out": global_totals["pledge_visa_out"],
                "pledge_visa_net": global_totals["pledge_visa_net"],
                "advance_deposits": global_totals["advance_deposits"],
                "advance_cash": global_totals["advance_cash"],
                "advance_visa": global_totals["advance_visa"],
                "advance_cash_count": global_totals["advance_cash_count"],
                "advance_visa_count": global_totals["advance_visa_count"],
                "advance_order_count": global_totals["advance_order_count"],
                "advance_order_total": global_totals["advance_order_total"],
                "advance_pickup_value": global_totals["advance_pickup_value"],
                "advance_remaining_amount": global_totals["advance_remaining_amount"],
                "advance_pending_count": global_totals["advance_pending_count"],
                "delivery_amount": global_totals["delivery_amount"],
                "order_count": global_totals["order_count"],
                "orders_per_min": global_totals["orders_per_min"],
                "attendant_employee_count": global_totals["attendant_employee_count"],
                "total_labor_cost": global_totals["total_labor_cost"],
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
        engine = self.env["pos.daily.ops.engine"]
        period = self._parse_period(date_from, date_to)
        configs = self._get_report_configs(config_ids)
        active_config_ids = set(configs.ids)
        sessions = engine._get_sessions(period, configs)

        # Clear previous transient drill-down records for current user
        self.env["pos.unified.report"].sudo().search([("create_uid", "=", self.env.user.id)]).unlink()

        vals_list = []

        if metric_type in PAYMENT_METRICS:
            for pay in engine._get_payments(sessions):
                pm = pay.payment_method_id
                if not self._payment_matches_metric(pm, metric_type):
                    continue
                bucket = engine._get_bucket(pm)
                cfg = pay.session_id.config_id
                po = pay.pos_order_id
                amt = pay.amount or 0.0

                untaxed_amt = tax_amt = order_disc = 0.0
                if po:
                    tot_amt_full = po.amount_total or 0.0
                    ratio = (amt / tot_amt_full) if tot_amt_full else 1.0
                    untaxed_amt = self._order_untaxed(po) * ratio
                    tax_amt = (po.amount_tax or 0.0) * ratio
                    order_disc = self._order_discount(po) * ratio

                is_online = bucket in DELIVERY_CHANNELS
                vals_list.append({
                    "name": po.name or pay.name or _("POS Payment"),
                    "date": pay.payment_date or (po.date_order if po else False) or pay.session_id.start_at,
                    "config_id": cfg.id,
                    "session_id": pay.session_id.id,
                    "payment_method_id": pm.id,
                    "pos_order_id": po.id or False,
                    "report_type": "online_sales" if is_online else "pos_sales",
                    "amount": amt,
                    "untaxed_amount": untaxed_amt,
                    "tax_amount": tax_amt,
                    "discount_amount": order_disc,
                    "employee_debt_amount": amt if bucket == "employee_debt" else 0.0,
                    "cash_amount": amt if bucket == "cash" else 0.0,
                    "visa_amount": amt if bucket == "visa" else 0.0,
                    "online_amount": amt if is_online else 0.0,
                    "partner_id": po.partner_id.id if po else False,
                    "company_id": cfg.company_id.id,
                })

        elif metric_type in ("untaxed_sales", "tax_amount", "discount_amount"):
            for order in engine._get_orders(sessions):
                cfg = order.config_id
                untaxed_amt = self._order_untaxed(order)
                tax_amt = order.amount_tax or 0.0
                order_disc = self._order_discount(order)

                amt = {
                    "untaxed_sales": untaxed_amt,
                    "tax_amount": tax_amt,
                    "discount_amount": order_disc,
                }[metric_type]

                if amt != 0.0:
                    vals_list.append({
                        "name": order.name or _("POS Order"),
                        "date": order.date_order,
                        "config_id": cfg.id,
                        "session_id": order.session_id.id,
                        "pos_order_id": order.id,
                        "report_type": "pos_sales",
                        "amount": order.amount_total or 0.0,
                        "untaxed_amount": untaxed_amt,
                        "tax_amount": tax_amt,
                        "discount_amount": order_disc,
                        "partner_id": order.partner_id.id or False,
                        "company_id": cfg.company_id.id,
                    })

        elif metric_type == "net_cash_moves":
            for st in engine._get_cash_move_lines(sessions):
                cfg = st.pos_session_id.config_id
                amt = st.amount or 0.0
                is_in = amt > 0
                vals_list.append({
                    "name": st.payment_ref or st.ref or st.name or _("Cash Move"),
                    "date": st.create_date or st.pos_session_id.start_at,
                    "config_id": cfg.id,
                    "session_id": st.pos_session_id.id,
                    "report_type": "cash_in" if is_in else "cash_out",
                    "amount": abs(amt),
                    "cash_in_amount": amt if is_in else 0.0,
                    "cash_out_amount": abs(amt) if not is_in else 0.0,
                    "partner_id": st.partner_id.id or False,
                    "company_id": cfg.company_id.id,
                })

        elif metric_type in ("net_pledges", "pledge_cash", "pledge_visa"):
            share_key = {"pledge_cash": "cash", "pledge_visa": "visa"}.get(metric_type, "amount")
            for move in self._get_pledge_movements(period, configs):
                share = move[share_key]
                if not share:
                    continue
                pledge = move["pledge"]
                cfg = move["config"]
                is_in = move["type"] == "in"
                sign = 1.0 if is_in else -1.0
                label = pledge.display_name or pledge.product_id.name
                vals_list.append({
                    "name": (_("Pledge Received: %s") if is_in else _("Pledge Returned: %s")) % label,
                    "date": move["date"],
                    "config_id": cfg.id,
                    "report_type": "rahen_in" if is_in else "rahen_out",
                    "payment_method_id": move["payment_method"].id or False,
                    "pos_order_id": move["pos_order"].id or False,
                    "amount": sign * share,
                    "rahen_in_amount": share if is_in else 0.0,
                    "rahen_out_amount": 0.0 if is_in else share,
                    "cash_amount": sign * move["cash"] if share_key in ("amount", "cash") else 0.0,
                    "visa_amount": sign * move["visa"] if share_key in ("amount", "visa") else 0.0,
                    "partner_id": pledge.partner_id.id or False,
                    "company_id": cfg.company_id.id,
                })

        elif metric_type in ("advance_deposits", "advance_cash", "advance_visa"):
            channel = {"advance_cash": "cash", "advance_visa": "visa"}.get(metric_type)
            for adv in self._get_advance_orders(period):
                if not engine._in_business_window(period, adv.create_date):
                    continue
                cfg = adv.from_pos_config_id or adv.pos_config_id
                if not cfg or cfg.id not in active_config_ids:
                    continue
                adv_channel = self._advance_channel(adv)
                if channel and adv_channel != channel:
                    continue
                amt = adv.advance_amount or 0.0
                vals_list.append({
                    "name": adv.name or _("Advance Order Deposit"),
                    "date": adv.create_date,
                    "config_id": cfg.id,
                    "report_type": "advance_deposit",
                    "payment_method_id": adv.pos_payment_method_id.id or False,
                    "pos_order_id": adv.advance_pos_order_id.id or False,
                    "amount": amt,
                    "advance_amount": amt,
                    "cash_amount": amt if adv_channel == "cash" else 0.0,
                    "visa_amount": amt if adv_channel == "visa" else 0.0,
                    "partner_id": adv.partner_id.id or False,
                    "company_id": cfg.company_id.id,
                })

        elif metric_type in ("attendant_employees", "labor_cost"):
            for att in self._get_attendances(period):
                emp = att.employee_id
                if not emp:
                    continue
                cfg = self._get_employee_pos_config(emp, configs)
                if not cfg or cfg.id not in active_config_ids:
                    continue
                daily_cost = self._employee_daily_cost(emp, att.check_in.date())
                vals_list.append({
                    "name": _("%s - Daily Wage (%s JOD)") % (emp.name, f"{daily_cost:.3f}"),
                    "date": att.check_in,
                    "config_id": cfg.id,
                    "report_type": "labor_cost" if metric_type == "labor_cost" else "attendant_employees",
                    "amount": daily_cost,
                    "labor_cost_amount": daily_cost,
                    "attendant_employee_count": 1,
                    "employee_id": emp.id,
                    "company_id": cfg.company_id.id,
                })

        if vals_list:
            self.env["pos.unified.report"].sudo().create(vals_list)

        wizard_vals = {"date_from": period["date_from"], "date_to": period["date_to"]}
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
            "net_pledges": _("Pledge (Rahen) In / Out Transactions"),
            "advance_deposits": _("Advance Order Deposit Transactions"),
            "pledge_cash": _("Pledge Cash (Received / Returned) Transactions"),
            "pledge_visa": _("Pledge Visa (Received / Returned) Transactions"),
            "advance_cash": _("Advance Cash Deposit Transactions"),
            "advance_visa": _("Advance Visa Deposit Transactions"),
            "attendant_employees": _("Attendant Employees Breakdown"),
            "labor_cost": _("Daily Employee Labor Cost Breakdown"),
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
