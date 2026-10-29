# -*- coding: utf-8 -*-
import logging
import math
from collections import defaultdict
from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.tools import SQL
from odoo.addons.pos_ameen_daily_operation.models.pos_daily_ops_engine import DELIVERY_CHANNELS

_logger = logging.getLogger(__name__)

EXCLUDED_CONFIG_KEYWORDS = ["كافيه", "نجيب", "ذوابي"]

EARTH_RADIUS_M = 6371000.0
# Mobile check-ins are accepted with up to 100 m GPS accuracy (anabtawi_mobile.max_location_accuracy_m).
GPS_TOLERANCE_M = 100.0

EXPLICIT_DEPT_TO_POS_MAP = {
    "شفا بدران": "فرع شفا بدران",
    "فرع ابونصير": "فرع ابونصير",
    "فرع اربد": "فرع اربد",
    "فرع السلط 1": "فرع السلط 1",
    "فرع السلط 2": "فرع السلط 2",
    "فرع الشويخ مول": "شويخ مول",
    "شويخ مول": "شويخ مول",
    "فرع الفحيص": "فرع الفحيص",
    "فرع القويسمة": "فرع القويسمة",
    "فرع الكرك": "فرع الكرك",
    "فرع المدينة المنورة": "فرع المدينة",
    "فرع المدينة": "فرع المدينة",
    "المدينة المنورة": "فرع المدينة",
    "فرع المقابلين": "المقابلين",
    "المقابلين": "المقابلين",
    "فرع الهاشمي": "فرع الهاشمي",
    "فرع ايلا": "ايلا",
    "ايلا": "ايلا",
    "فرع شارع البيتزا": "فرع البتزا",
    "شارع البيتزا": "فرع البتزا",
    "فرع البتزا": "فرع البتزا",
    "فرع صويلح": "فرع صويلح",
    "فرع عريفة مول": "فرع عريفة مول",
    "فرع عين الباشا": "فرع عين الباشا",
    "فرع مادبا": "فرع مادبا",
    "فرع ماركا": "فرع ماركا",
    "فرع مرج الحمام": "فرع مرج الحمام",
    "فرع الإذاعة": "فرع الإذاعة",
    "الإذاعة": "فرع الإذاعة",
}

DASHBOARD_EXTRA_KEYS = {
    "untaxed_sales": 0.0,
    "tax_amount": 0.0,
    "cash_untaxed": 0.0,
    "visa_untaxed": 0.0,
    "online_sales_untaxed": 0.0,
    "employee_debt_untaxed": 0.0,
    "other_sales_untaxed": 0.0,
    "discount_amount": 0.0,
    "gift_amount": 0.0,
    "gift_line_count": 0,
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
    "open_hours": 0.0,
    "orders_per_hour": 0.0,
    "paying_order_count": 0,
    "avg_basket": 0.0,
    "expense_amount": 0.0,
    "expense_count": 0,
    "expense_pending_amount": 0.0,
    "expense_pending_count": 0,
    "attendant_employee_count": 0,
    "total_labor_cost": 0.0,
    "extra_hours": 0.0,
    "extra_hours_amount": 0.0,
    "unapproved_extra_hours": 0.0,
    "unapproved_extra_hours_amount": 0.0,
}

PAYMENT_METRICS = ("sales", "cash_sales", "visa_sales", "employee_debt", "online_sales", "hospitality")


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

    @staticmethod
    def _period_bounds(period):
        """Naive UTC business window (06:00 -> 06:00 local) and its string form."""
        dt_start, dt_end = period["business_start"], period["business_end"]
        return dt_start, dt_end, fields.Datetime.to_string(dt_start), fields.Datetime.to_string(dt_end)

    def _get_pledge_movements(self, period, configs):
        return self.env["pos.daily.ops.engine"]._get_pledge_movements(period, configs)

    def _get_advance_orders(self, period):
        start, end = period["business_start"], period["business_end"]
        return self.env["pos.advance.order"].sudo().search([
            ("state", "not in", ("draft", "cancel")),
            "|",
            "&", ("create_date", ">=", start), ("create_date", "<", end),
            "&", ("picking_date", ">=", start), ("picking_date", "<", end),
        ])

    def _get_report_configs(self, config_ids=None):
        """Active retail branches of the active companies (cafe/corporate configs excluded)."""
        domain = [
            ("active", "=", True),
            ("company_id", "in", self.env.companies.ids),
        ]
        for kw in EXCLUDED_CONFIG_KEYWORDS:
            domain.append(("name", "not ilike", kw))
        if config_ids and isinstance(config_ids, (list, tuple)) and len(config_ids) > 0:
            domain.append(("id", "in", config_ids))
        return self.env["pos.config"].sudo().search(domain, order="name")

    def _advance_channel(self, adv):
        """'cash' or 'visa' for an advance order deposit."""
        channel = self.env["pos.daily.ops.engine"]._get_channel(adv.pos_payment_method_id)
        if channel:
            return channel
        return "cash" if (adv.payment_method or "cash") == "cash" else "visa"

    @staticmethod
    def _gift_line_value(line):
        return (line.price_unit or 0.0) * (line.qty or 0.0)

    @staticmethod
    def _order_discount(order):
        """Real discounts only; gift lines are reported separately."""
        return sum(
            (line.price_unit or 0.0) * (line.qty or 0.0) * (line.discount / 100.0)
            for line in order.lines if line.discount and not line.is_gift
        )

    def _order_gift_lines(self, order):
        return order.lines.filtered("is_gift")

    @staticmethod
    def _order_untaxed(order):
        untaxed = getattr(order, "amount_untaxed", None)
        if untaxed is None:
            untaxed = (order.amount_total or 0.0) - (order.amount_tax or 0.0)
        return untaxed

    @staticmethod
    def _payment_tax_split(payment):
        """(untaxed, tax) share of a payment in its order; both add up to the payment amount."""
        amount = payment.amount or 0.0
        order = payment.pos_order_id
        if not order or not order.amount_total:
            return amount, 0.0
        tax = (order.amount_tax or 0.0) * amount / order.amount_total
        return amount - tax, tax

    def _channel_untaxed_key(self, payment_method):
        """Branch key that receives the untaxed share of an income payment."""
        bucket = self.env["pos.daily.ops.engine"]._get_bucket(payment_method)
        return self._channel_untaxed_key_from_bucket(bucket)

    @staticmethod
    def _channel_untaxed_key_from_bucket(bucket):
        if bucket == "cash":
            return "cash_untaxed"
        if bucket == "visa":
            return "visa_untaxed"
        if bucket == "employee_debt":
            return "employee_debt_untaxed"
        if bucket in DELIVERY_CHANNELS:
            return "online_sales_untaxed"
        return "other_sales_untaxed"

    def _accumulate_order_metrics(self, sessions, branch_data):
        """Tax, discounts, gifts and order counts for the period's sessions.

        A range longer than a month is too many payments and lines to walk in
        Python before the worker time limit. The totals below follow the same
        rules as those loops, in three SQL aggregates.
        """
        if not sessions:
            return
        session_ids = tuple(sessions.ids)
        excluded = ("hospitality", "advance_applied")
        self.env["pos.payment"].flush_model(["amount", "session_id", "pos_order_id", "payment_method_id"])
        self.env["pos.order"].flush_model(["config_id", "session_id", "state", "amount_total", "amount_tax"])
        self.env["pos.order.line"].flush_model(["order_id", "price_unit", "qty", "discount", "is_gift"])
        self.env["pos.payment.method"].flush_model(["daily_ops_report_type"])
        self.env["pos.session"].flush_model(["config_id"])

        self.env.cr.execute(SQL("""
            SELECT sess.config_id,
                   COALESCE(pm.daily_ops_report_type, 'none') AS bucket,
                   SUM(
                       CASE
                           WHEN ord.amount_total IS NULL OR ord.amount_total = 0 THEN COALESCE(pay.amount, 0)
                           ELSE COALESCE(pay.amount, 0)
                                - (COALESCE(ord.amount_tax, 0) * COALESCE(pay.amount, 0) / ord.amount_total)
                       END
                   ) AS untaxed,
                   SUM(
                       CASE
                           WHEN ord.amount_total IS NULL OR ord.amount_total = 0 THEN 0
                           ELSE COALESCE(ord.amount_tax, 0) * COALESCE(pay.amount, 0) / ord.amount_total
                       END
                   ) AS tax
              FROM pos_payment pay
              JOIN pos_session sess ON sess.id = pay.session_id
              LEFT JOIN pos_order ord ON ord.id = pay.pos_order_id
              LEFT JOIN pos_payment_method pm ON pm.id = pay.payment_method_id
             WHERE pay.session_id IN %(session_ids)s
               AND COALESCE(pm.daily_ops_report_type, 'none') NOT IN %(excluded)s
             GROUP BY sess.config_id, COALESCE(pm.daily_ops_report_type, 'none')
        """, session_ids=session_ids, excluded=excluded))
        for config_id, bucket, untaxed, tax in self.env.cr.fetchall():
            if not config_id:
                continue
            branch = branch_data[config_id]
            branch["untaxed_sales"] += float(untaxed or 0.0)
            branch["tax_amount"] += float(tax or 0.0)
            branch[self._channel_untaxed_key_from_bucket(bucket)] += float(untaxed or 0.0)

        self.env.cr.execute(SQL("""
            SELECT ord.config_id, COUNT(*)
              FROM pos_order ord
              JOIN (
                    SELECT pay.pos_order_id AS order_id
                      FROM pos_payment pay
                      LEFT JOIN pos_payment_method pm ON pm.id = pay.payment_method_id
                     WHERE pay.session_id IN %(session_ids)s
                       AND pay.pos_order_id IS NOT NULL
                       AND COALESCE(pm.daily_ops_report_type, 'none') NOT IN %(excluded)s
                     GROUP BY pay.pos_order_id
                    HAVING SUM(COALESCE(pay.amount, 0)) > 0.0005
              ) inc ON inc.order_id = ord.id
             GROUP BY ord.config_id
        """, session_ids=session_ids, excluded=excluded))
        for config_id, count in self.env.cr.fetchall():
            if config_id:
                branch_data[config_id]["paying_order_count"] += count or 0

        self.env.cr.execute(SQL("""
            SELECT ord.config_id,
                   COUNT(DISTINCT ord.id) AS order_count,
                   COALESCE(SUM(
                       CASE
                           WHEN line.is_gift IS NOT TRUE AND COALESCE(line.discount, 0) != 0
                           THEN COALESCE(line.price_unit, 0) * COALESCE(line.qty, 0) * line.discount / 100.0
                           ELSE 0
                       END
                   ), 0) AS discount_amount,
                   COALESCE(SUM(
                       CASE
                           WHEN line.is_gift IS TRUE
                           THEN COALESCE(line.price_unit, 0) * COALESCE(line.qty, 0)
                           ELSE 0
                       END
                   ), 0) AS gift_amount,
                   COALESCE(SUM(CASE WHEN line.is_gift IS TRUE THEN 1 ELSE 0 END), 0) AS gift_line_count
              FROM pos_order ord
              LEFT JOIN pos_order_line line ON line.order_id = ord.id
             WHERE ord.session_id IN %(session_ids)s
               AND ord.state IN ('paid', 'done', 'invoiced')
             GROUP BY ord.config_id
        """, session_ids=session_ids))
        for config_id, order_count, discount_amount, gift_amount, gift_line_count in self.env.cr.fetchall():
            if not config_id:
                continue
            branch = branch_data[config_id]
            branch["order_count"] += order_count or 0
            branch["discount_amount"] += float(discount_amount or 0.0)
            branch["gift_amount"] += float(gift_amount or 0.0)
            branch["gift_line_count"] += gift_line_count or 0

    def _get_paying_orders(self, sessions):
        """{pos.order: income} for orders whose income payments are above zero
        (hospitality-only, refund and zero-total gift orders excluded)."""
        engine = self.env["pos.daily.ops.engine"]
        order_income = defaultdict(float)
        for pay in engine._get_payments(sessions):
            if pay.pos_order_id and engine._is_in_sales(pay.payment_method_id):
                order_income[pay.pos_order_id] += pay.amount or 0.0
        return {order: income for order, income in order_income.items() if income > 0.0005}

    @staticmethod
    def _avg_basket(values):
        if not values["paying_order_count"]:
            return 0.0
        return round(values["sales"] / values["paying_order_count"], 3)

    def _get_session_expenses(self, sessions):
        """POS expenses created in the period's sessions (same day rule as sales)."""
        if "pos.expense" not in self.env:
            return False
        Expense = self.env["pos.expense"].sudo()
        if not sessions:
            return Expense.browse()
        return Expense.search([("session_id", "in", sessions.ids)])

    def _open_expense_drilldown(self, sessions, active_config_ids):
        """Open pos.expense list/form for the dashboard period (and optional branch filter)."""
        expenses = self._get_session_expenses(sessions)
        if expenses:
            expenses = expenses.filtered(lambda e: e.config_id.id in active_config_ids)
            expense_ids = expenses.ids
        else:
            expense_ids = []

        list_view = self.env.ref(
            "anabtawi_pos_expense.view_pos_expense_list", raise_if_not_found=False
        )
        form_view = self.env.ref(
            "anabtawi_pos_expense.view_pos_expense_form", raise_if_not_found=False
        )
        views = []
        if list_view:
            views.append((list_view.id, "list"))
        if form_view:
            views.append((form_view.id, "form"))

        return {
            "name": _("POS Expenses"),
            "type": "ir.actions.act_window",
            "res_model": "pos.expense",
            "view_mode": "list,form",
            "views": views if views else [(False, "list"), (False, "form")],
            "domain": [("id", "in", expense_ids)] if expense_ids else [("id", "=", 0)],
            "target": "current",
            "context": {"create": False, "delete": False},
        }

    @staticmethod
    def _orders_per_hour(values):
        if values["open_hours"] <= 0:
            return 0.0
        return round(values["order_count"] / values["open_hours"], 2)

    def _payment_matches_metric(self, payment_method, metric_type):
        bucket = self.env["pos.daily.ops.engine"]._get_bucket(payment_method)
        if metric_type == "sales":
            return self.env["pos.daily.ops.engine"]._is_in_sales(payment_method)
        if metric_type == "cash_sales":
            return bucket == "cash"
        if metric_type == "visa_sales":
            return bucket == "visa"
        if metric_type == "employee_debt":
            return bucket == "employee_debt"
        if metric_type == "online_sales":
            return bucket in DELIVERY_CHANNELS
        if metric_type == "hospitality":
            return bucket == "hospitality"
        return False

    def _get_employee_pos_config(self, emp, configs):
        """Map an employee to a POS branch via department path & work location names."""
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

        # Check explicit mapping dictionary first
        mapped_target = EXPLICIT_DEPT_TO_POS_MAP.get(leaf_dept_name) or EXPLICIT_DEPT_TO_POS_MAP.get(dept_full_path)
        if mapped_target:
            target_clean = mapped_target.strip().lower()
            for cfg in configs:
                cfg_name = (cfg.name or "").strip().lower()
                if cfg_name == target_clean or (len(target_clean) >= 3 and target_clean in cfg_name) or (len(cfg_name) >= 3 and cfg_name in target_clean):
                    return cfg

        clean_leaf = leaf_dept_name.lower().strip()
        clean_full = dept_full_path.lower().strip()
        clean_loc = loc_name.lower().strip()

        def _normalize(s):
            if not s:
                return ""
            for noise in ("فرع ", "فرع", "شارع ", "شارع", "منطقة ", "منطقة", "مول"):
                s = s.replace(noise, "")
            return s.strip().lower()

        norm_leaf = _normalize(leaf_dept_name)
        norm_loc = _normalize(loc_name)

        # Tier 1: Exact match on leaf department name or work location
        if clean_leaf or clean_loc:
            for cfg in configs:
                cfg_name = (cfg.name or "").strip().lower()
                if (clean_leaf and cfg_name == clean_leaf) or (clean_loc and cfg_name == clean_loc):
                    return cfg

        # Tier 2: Normalized keyword matching (minimum 3 characters to prevent empty string matching)
        if (norm_leaf and len(norm_leaf) >= 3) or (norm_loc and len(norm_loc) >= 3):
            for cfg in configs:
                norm_cfg = _normalize(cfg.name or "")
                if norm_cfg and len(norm_cfg) >= 3:
                    if (norm_leaf and len(norm_leaf) >= 3 and (norm_leaf in norm_cfg or norm_cfg in norm_leaf)) or \
                       (norm_loc and len(norm_loc) >= 3 and (norm_loc in norm_cfg or norm_cfg in norm_loc)):
                        return cfg

        # Tier 3: Leaf department name or work location contained in POS config name (minimum 3 chars)
        if (clean_leaf and len(clean_leaf) >= 3) or (clean_loc and len(clean_loc) >= 3):
            for cfg in configs:
                cfg_name = (cfg.name or "").strip().lower()
                if len(cfg_name) >= 3:
                    if clean_leaf and (clean_leaf in cfg_name or cfg_name in clean_leaf):
                        return cfg
                    if clean_loc and (clean_loc in cfg_name or cfg_name in clean_loc):
                        return cfg

        # Tier 4: POS config name contained within full department path (minimum 3 chars)
        if clean_full and len(clean_full) >= 3:
            for cfg in configs:
                cfg_name = (cfg.name or "").strip().lower()
                if cfg_name and len(cfg_name) >= 3 and cfg_name in clean_full:
                    return cfg

        return False

    def _get_branch_geo_locations(self):
        """Work locations linked to a POS branch that have GPS coordinates."""
        return self.env["hr.work.location"].sudo().search([
            ("pos_config_id", "!=", False),
            ("attendance_geo_latitude", "!=", 0.0),
            ("attendance_geo_longitude", "!=", 0.0),
        ])

    @staticmethod
    def _distance_m(lat1, lon1, lat2, lon2):
        """Great-circle distance in meters (haversine)."""
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lambda = math.radians(lon2 - lon1)
        a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
        return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))

    def _get_check_in_location(self, att, geo_locations):
        """Nearest branch work location whose radius (plus GPS tolerance) contains the check-in point."""
        lat, lon = att.in_latitude, att.in_longitude
        if not geo_locations or not lat or not lon:
            return self.env["hr.work.location"]
        best, best_dist = self.env["hr.work.location"], None
        for loc in geo_locations:
            dist = self._distance_m(lat, lon, loc.attendance_geo_latitude, loc.attendance_geo_longitude)
            if dist > (loc.attendance_geo_radius_m or 0.0) + GPS_TOLERANCE_M:
                continue
            if best_dist is None or dist < best_dist:
                best, best_dist = loc, dist
        return best

    def _get_attendance_pos_config(self, att, configs, geo_locations):
        """(POS branch, check-in work location): GPS location first, employee profile as fallback."""
        location = self._get_check_in_location(att, geo_locations)
        if location:
            return location.pos_config_id, location
        return self._get_employee_pos_config(att.employee_id, configs), location

    @staticmethod
    def _is_administration_employee(emp):
        return bool(emp.work_location_id.is_administration)

    @api.model
    def get_dashboard_data(self, date_from=None, date_to=None, config_ids=None):
        """
        Fetch executive POS metrics across branch configurations for active multi-company context.
        Sales, payment channels, cash moves and pledges come from the shared Daily Operations
        engine so they always match the Daily Operations Excel report.
        """
        engine = self.env["pos.daily.ops.engine"]
        period = self._parse_period(date_from, date_to)
        dt_start, dt_end, str_start, str_end = self._period_bounds(period)

        configs = self._get_report_configs(config_ids)
        active_config_ids = set(configs.ids)

        sessions = engine._get_sessions(period, configs)
        figures = engine._compute_branch_figures(period, configs, sessions=sessions)

        def _empty_branch_dict():
            return {**engine._empty_figures(), **DASHBOARD_EXTRA_KEYS}

        branch_data = defaultdict(_empty_branch_dict)
        for cfg_id, values in figures.items():
            branch_data[cfg_id].update(values)

        # Tax, discounts, gifts and order counts. Same rules as the old per-record
        # loops, aggregated in SQL so a range longer than a month still returns.
        self._accumulate_order_metrics(sessions, branch_data)

        # Open time of the sessions; a session still open counts until now.
        now = fields.Datetime.now()
        for session in sessions:
            if not session.start_at:
                continue
            session_end = session.stop_at or now
            branch_data[session.config_id.id]["open_hours"] += max(
                (session_end - session.start_at).total_seconds() / 3600.0, 0.0
            )

        for cfg_id in active_config_ids:
            branch = branch_data[cfg_id]
            branch["net_cash_moves"] = branch["cash_in"] - branch["cash_out"]
            branch["net_pledges"] = branch["rahen_in"] - branch["rahen_out"]
            branch["pledge_cash_net"] = branch["pledge_cash_in"] - branch["pledge_cash_out"]
            branch["pledge_visa_net"] = branch["pledge_visa_in"] - branch["pledge_visa_out"]
            branch["orders_per_hour"] = self._orders_per_hour(branch)
            branch["avg_basket"] = self._avg_basket(branch)

        # --- D2. POS Expenses (approved = KPI; to_approve + refused = pending badge) ---
        expenses = self._get_session_expenses(sessions)
        if expenses:
            for expense in expenses:
                cfg = expense.config_id
                if not cfg or (active_config_ids and cfg.id not in active_config_ids):
                    continue
                branch = branch_data[cfg.id]
                amt = expense.amount or 0.0
                if expense.state == "approved":
                    branch["expense_amount"] += amt
                    branch["expense_count"] += 1
                elif expense.state in ("to_approve", "refused"):
                    branch["expense_pending_amount"] += amt
                    branch["expense_pending_count"] += 1

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
                        channel = self._advance_channel(adv)
                        branch_data[orig_cfg_id]["advance_%s" % channel] += dep_amt
                        branch_data[orig_cfg_id]["advance_%s_count" % channel] += 1

                if adv.picking_date and dt_start <= adv.picking_date <= dt_end:
                    if pick_cfg_id and (not active_config_ids or pick_cfg_id in active_config_ids):
                        branch_data[pick_cfg_id]["advance_pickup_value"] += tot_amt
                        branch_data[pick_cfg_id]["advance_remaining_amount"] += rem_amt
                        if adv.state in ("confirmed", "advance_paid"):
                            branch_data[pick_cfg_id]["advance_pending_count"] += 1



        # --- F. Collect Attendance & Calculate Daily Employee Labor Cost ---
        if "hr.attendance" in self.env:
            import calendar
            search_start = datetime.combine(dt_start.date() - timedelta(days=1), time.min)
            search_end = datetime.combine(dt_end.date() + timedelta(days=1), time.max)
            attendances = self.env["hr.attendance"].sudo().search([
                ("check_in", ">=", search_start),
                ("check_in", "<=", search_end),
            ])
            branch_daily_attendants = defaultdict(lambda: defaultdict(set))
            branch_extra_hours = defaultdict(float)
            branch_extra_hours_amount = defaultdict(float)
            branch_unapproved_extra_hours = defaultdict(float)
            branch_unapproved_extra_hours_amount = defaultdict(float)
            geo_locations = self._get_branch_geo_locations()

            for att in attendances:
                emp = att.employee_id
                if not emp or not att.check_in or self._is_administration_employee(emp):
                    continue
                c_dt = att.check_in
                local_c_dt = fields.Datetime.context_timestamp(self, c_dt) if c_dt else False
                att_date = local_c_dt.date() if local_c_dt else c_dt.date()
                if not (dt_start <= c_dt <= dt_end):
                    continue
                cfg, _location = self._get_attendance_pos_config(att, configs, geo_locations)
                if not cfg or (active_config_ids and cfg.id not in active_config_ids):
                    continue
                branch_daily_attendants[cfg.id][att_date].add(emp)

                # Overtime Breakdown: Approved vs Not Approved
                approved_ot = 0.0
                unapproved_ot = 0.0
                if hasattr(att, "linked_overtime_ids") and att.linked_overtime_ids:
                    for line in att.linked_overtime_ids:
                        dur = line.manual_duration or line.duration or 0.0
                        if line.status == "approved":
                            approved_ot += dur
                        else:
                            unapproved_ot += dur
                if approved_ot == 0.0 and hasattr(att, "validated_overtime_hours"):
                    approved_ot = getattr(att, "validated_overtime_hours", 0.0) or 0.0
                total_ot = getattr(att, "overtime_hours", 0.0) or getattr(att, "extra_hours", 0.0) or 0.0
                if unapproved_ot == 0.0 and total_ot > approved_ot:
                    unapproved_ot = total_ot - approved_ot

                # Calculate Hourly Rate from monthly wage & standard 8-hour workday
                wage = getattr(emp, "wage", 0.0) or (
                    emp.contract_id.wage if (hasattr(emp, "contract_id") and emp.contract_id and emp.contract_id.wage) else 0.0
                ) or 0.0
                num_days = calendar.monthrange(att_date.year, att_date.month)[1] if att_date else 30
                daily_cost = wage / float(num_days) if num_days > 0 else 0.0
                hourly_rate = daily_cost / 8.0 if daily_cost > 0 else 0.0

                approved_amt = approved_ot * hourly_rate
                unapproved_amt = unapproved_ot * hourly_rate

                branch_extra_hours[cfg.id] += approved_ot
                branch_extra_hours_amount[cfg.id] += approved_amt
                branch_unapproved_extra_hours[cfg.id] += unapproved_ot
                branch_unapproved_extra_hours_amount[cfg.id] += unapproved_amt

            for cfg_id, daily_map in branch_daily_attendants.items():
                all_attending_emp_ids = set()
                total_cost = 0.0
                for att_date, emp_set in daily_map.items():
                    all_attending_emp_ids.update(e.id for e in emp_set)
                    num_days = calendar.monthrange(att_date.year, att_date.month)[1]
                    for emp in emp_set:
                        wage = getattr(emp, "wage", 0.0) or (
                            emp.contract_id.wage if (hasattr(emp, "contract_id") and emp.contract_id and emp.contract_id.wage) else 0.0
                        ) or 0.0
                        daily_cost = wage / float(num_days) if num_days > 0 else 0.0
                        total_cost += daily_cost

                branch_data[cfg_id]["attendant_employee_count"] = len(all_attending_emp_ids)
                branch_data[cfg_id]["total_labor_cost"] = round(total_cost, 3)
                branch_data[cfg_id]["extra_hours"] = round(branch_extra_hours[cfg_id], 2)
                branch_data[cfg_id]["extra_hours_amount"] = round(branch_extra_hours_amount[cfg_id], 3)
                branch_data[cfg_id]["unapproved_extra_hours"] = round(branch_unapproved_extra_hours[cfg_id], 2)
                branch_data[cfg_id]["unapproved_extra_hours_amount"] = round(branch_unapproved_extra_hours_amount[cfg_id], 3)

        # --- G. Build Rows & Global Totals ---
        branch_rows = []
        global_totals = _empty_branch_dict()

        for config in configs:
            vals = branch_data[config.id]
            row = {"config_id": config.id, "branch_name": config.name, **vals}
            branch_rows.append(row)

            for key in global_totals.keys():
                global_totals[key] += vals[key]

        # Average per branch: all orders over the open hours of all sessions.
        global_totals["orders_per_hour"] = self._orders_per_hour(global_totals)
        global_totals["avg_basket"] = self._avg_basket(global_totals)

        # --- G. Build Channel Distribution & Daily Trends ---
        channels = [
            {"name": _("Cash Sales"), "value": global_totals["cash_untaxed"], "color": "#28a745"},
            {"name": _("Visa / Card"), "value": global_totals["visa_untaxed"], "color": "#007bff"},
            {"name": _("Online & Delivery"), "value": global_totals["online_sales_untaxed"], "color": "#fd7e14"},
            {"name": _("Debt Sales (مبيعات الذمم)"), "value": global_totals["employee_debt_untaxed"], "color": "#6f42c1"},
            {"name": _("Other Channels"), "value": global_totals["other_sales_untaxed"], "color": "#6c757d"},
        ]
        channels_filtered = [c for c in channels if c["value"] > 0]

        # Daily trends (by business date of the session)
        day_totals = defaultdict(lambda: {"total": 0.0, "cash": 0.0, "visa": 0.0})
        if sessions:
            groups = self.env["pos.payment"].sudo()._read_group(
                [("session_id", "in", sessions.ids)],
                ["session_id", "payment_method_id"],
                ["amount:sum"],
            )
            for session, payment_method, amount in groups:
                if not engine._is_in_sales(payment_method):
                    continue
                bucket = engine._get_bucket(payment_method)
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

        all_config_domain = [
            ("active", "=", True),
            ("company_id", "in", self.env.companies.ids),
        ]
        for kw in EXCLUDED_CONFIG_KEYWORDS:
            all_config_domain.append(("name", "not ilike", kw))

        all_configs = self.env["pos.config"].sudo().search(all_config_domain, order="name")
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
                "gift_amount": global_totals["gift_amount"],
                "gift_line_count": global_totals["gift_line_count"],
                "cash_sales": global_totals["cash"],
                "visa_sales": global_totals["visa"],
                "online_sales": global_totals["online_sales"],
                "employee_debt": global_totals["employee_debt"],
                "cash_sales_untaxed": global_totals["cash_untaxed"],
                "visa_sales_untaxed": global_totals["visa_untaxed"],
                "online_sales_untaxed": global_totals["online_sales_untaxed"],
                "employee_debt_untaxed": global_totals["employee_debt_untaxed"],
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
                "orders_per_hour": global_totals["orders_per_hour"],
                "avg_basket": global_totals["avg_basket"],
                "paying_order_count": global_totals["paying_order_count"],
                "open_hours": global_totals["open_hours"],
                "expense_amount": global_totals["expense_amount"],
                "expense_count": global_totals["expense_count"],
                "expense_pending_amount": global_totals["expense_pending_amount"],
                "expense_pending_count": global_totals["expense_pending_count"],
                "attendant_employee_count": global_totals["attendant_employee_count"],
                "total_labor_cost": global_totals["total_labor_cost"],
                "total_extra_hours": global_totals["extra_hours"],
                "total_extra_hours_amount": global_totals["extra_hours_amount"],
                "unapproved_extra_hours": global_totals["unapproved_extra_hours"],
                "unapproved_extra_hours_amount": global_totals["unapproved_extra_hours_amount"],
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
        dt_start, dt_end, str_start, str_end = self._period_bounds(period)

        configs = self._get_report_configs(config_ids)
        active_config_ids = set(configs.ids)
        sessions = engine._get_sessions(period, configs)

        # Open native POS Expenses list/form (type, status, amount) instead of unified report.
        if metric_type == "expense_amount":
            return self._open_expense_drilldown(sessions, active_config_ids)

        all_config_domain = [
            ("active", "=", True),
            ("company_id", "in", self.env.companies.ids),
        ]
        for kw in EXCLUDED_CONFIG_KEYWORDS:
            all_config_domain.append(("name", "not ilike", kw))

        all_configs = self.env["pos.config"].sudo().search(all_config_domain)

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

                untaxed_amt, tax_amt = self._payment_tax_split(pay)
                order_disc = 0.0
                if po and po.amount_total:
                    order_disc = self._order_discount(po) * amt / po.amount_total

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

        elif metric_type in ("untaxed_sales", "tax_amount"):
            for pay in engine._get_payments(sessions):
                pm = pay.payment_method_id
                if not engine._is_in_sales(pm):
                    continue
                untaxed_amt, tax_amt = self._payment_tax_split(pay)
                if (untaxed_amt if metric_type == "untaxed_sales" else tax_amt) == 0.0:
                    continue
                po = pay.pos_order_id
                cfg = pay.session_id.config_id
                vals_list.append({
                    "name": po.name or pay.name or _("POS Payment"),
                    "date": pay.payment_date or (po.date_order if po else False) or pay.session_id.start_at,
                    "config_id": cfg.id,
                    "session_id": pay.session_id.id,
                    "payment_method_id": pm.id,
                    "pos_order_id": po.id or False,
                    "report_type": "pos_sales",
                    "amount": pay.amount or 0.0,
                    "untaxed_amount": untaxed_amt,
                    "tax_amount": tax_amt,
                    "partner_id": po.partner_id.id if po else False,
                    "company_id": cfg.company_id.id,
                })

        elif metric_type == "discount_amount":
            for order in engine._get_orders(sessions):
                cfg = order.config_id
                untaxed_amt = self._order_untaxed(order)
                tax_amt = order.amount_tax or 0.0
                order_disc = self._order_discount(order)

                if order_disc != 0.0:
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

        elif metric_type == "avg_basket":
            for order, income in self._get_paying_orders(sessions).items():
                cfg = order.config_id
                vals_list.append({
                    "name": order.name or _("POS Order"),
                    "date": order.date_order,
                    "config_id": cfg.id,
                    "session_id": order.session_id.id,
                    "pos_order_id": order.id,
                    "report_type": "pos_sales",
                    "amount": income,
                    "partner_id": order.partner_id.id or False,
                    "company_id": cfg.company_id.id,
                })

        elif metric_type == "gift_amount":
            for order in engine._get_orders(sessions):
                cfg = order.config_id
                for line in self._order_gift_lines(order):
                    value = self._gift_line_value(line)
                    label = "%s x %s" % (line.product_id.display_name, line.qty)
                    if line.gift_reason:
                        label = "%s (%s)" % (label, line.gift_reason)
                    vals_list.append({
                        "name": label,
                        "date": order.date_order,
                        "config_id": cfg.id,
                        "session_id": order.session_id.id,
                        "pos_order_id": order.id,
                        "report_type": "gift",
                        "amount": value,
                        "gift_amount": value,
                        "partner_id": order.partner_id.id or False,
                        "company_id": cfg.company_id.id,
                    })

        elif metric_type in ("net_cash_moves", "cash_in", "cash_out"):
            for st in engine._get_cash_move_lines(sessions):
                cfg = st.pos_session_id.config_id
                amt = st.amount or 0.0
                is_in = amt > 0
                if metric_type == "cash_in" and not is_in:
                    continue
                if metric_type == "cash_out" and is_in:
                    continue
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

        elif metric_type in ("net_pledges", "rahen_in", "rahen_out", "pledge_cash", "pledge_visa"):
            share_key = {"pledge_cash": "cash", "pledge_visa": "visa"}.get(metric_type, "amount")
            only_type = {"rahen_in": "in", "rahen_out": "out"}.get(metric_type)
            for move in self._get_pledge_movements(period, configs):
                if only_type and move["type"] != only_type:
                    continue
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

        elif metric_type in ("advance_cash", "advance_visa"):
            channel = "cash" if metric_type == "advance_cash" else "visa"
            if "pos.advance.order" in self.env:
                adv_orders = self.env["pos.advance.order"].sudo().search([
                    ("state", "not in", ("draft", "cancel")),
                    ("create_date", ">=", str_start),
                    ("create_date", "<=", str_end),
                ])
                for adv in adv_orders:
                    cfg = adv.from_pos_config_id or adv.pos_config_id
                    if not cfg or cfg.id not in active_config_ids:
                        continue
                    if self._advance_channel(adv) != channel:
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
                        "cash_amount": amt if channel == "cash" else 0.0,
                        "visa_amount": amt if channel == "visa" else 0.0,
                        "partner_id": adv.partner_id.id or False,
                        "company_id": cfg.company_id.id,
                    })

        elif metric_type in ("attendant_employees", "labor_cost", "extra_hours", "unapproved_extra_hours"):
            if "hr.attendance" in self.env:
                import calendar
                search_start = datetime.combine(dt_start.date() - timedelta(days=1), time.min)
                search_end = datetime.combine(dt_end.date() + timedelta(days=1), time.max)
                attendances = self.env["hr.attendance"].sudo().search([
                    ("check_in", ">=", search_start),
                    ("check_in", "<=", search_end),
                ])
                geo_locations = self._get_branch_geo_locations()
                for att in attendances:
                    emp = att.employee_id
                    if not emp or not att.check_in or self._is_administration_employee(emp):
                        continue
                    c_dt = att.check_in
                    local_c_dt = fields.Datetime.context_timestamp(self, c_dt) if c_dt else False
                    att_date = local_c_dt.date() if local_c_dt else c_dt.date()
                    if not (dt_start <= c_dt <= dt_end):
                        continue
                    cfg, location = self._get_attendance_pos_config(att, all_configs, geo_locations)
                    if not cfg or (active_config_ids and cfg.id not in active_config_ids):
                        continue

                    # Overtime Breakdown: Approved vs Not Approved
                    approved_ot = 0.0
                    unapproved_ot = 0.0
                    if hasattr(att, "linked_overtime_ids") and att.linked_overtime_ids:
                        for line in att.linked_overtime_ids:
                            dur = line.manual_duration or line.duration or 0.0
                            if line.status == "approved":
                                approved_ot += dur
                            else:
                                unapproved_ot += dur
                    if approved_ot == 0.0 and hasattr(att, "validated_overtime_hours"):
                        approved_ot = getattr(att, "validated_overtime_hours", 0.0) or 0.0
                    total_ot = getattr(att, "overtime_hours", 0.0) or getattr(att, "extra_hours", 0.0) or 0.0
                    if unapproved_ot == 0.0 and total_ot > approved_ot:
                        unapproved_ot = total_ot - approved_ot

                    emp_code = (
                        getattr(emp, "employee_number", None)
                        or getattr(emp, "barcode", None)
                        or getattr(emp, "registration_number", None)
                        or (str(emp.id) if emp.id else "")
                    )
                    num_days = calendar.monthrange(att_date.year, att_date.month)[1] if att_date else 30
                    wage = getattr(emp, "wage", 0.0) or (
                        emp.contract_id.wage if (hasattr(emp, "contract_id") and emp.contract_id and emp.contract_id.wage) else 0.0
                    ) or 0.0
                    daily_cost = wage / float(num_days) if num_days > 0 else 0.0
                    hourly_rate = daily_cost / 8.0 if daily_cost > 0 else 0.0

                    if metric_type == "extra_hours":
                        if approved_ot <= 0:
                            continue
                        rec_amt = round(approved_ot * hourly_rate, 3)
                        rec_name = _("[%s] %s - Approved Extra Hours (%s hrs)") % (emp_code, emp.name, f"{approved_ot:.2f}")
                        ot_hrs = approved_ot
                    elif metric_type == "unapproved_extra_hours":
                        if unapproved_ot <= 0:
                            continue
                        rec_amt = round(unapproved_ot * hourly_rate, 3)
                        rec_name = _("[%s] %s - Not Approved Extra Hours (%s hrs)") % (emp_code, emp.name, f"{unapproved_ot:.2f}")
                        ot_hrs = unapproved_ot
                    elif metric_type == "labor_cost":
                        rec_name = _("[%s] %s - Daily Wage (%s JOD)") % (emp_code, emp.name, f"{daily_cost:.3f}")
                        rec_amt = daily_cost
                        ot_hrs = approved_ot
                    else:
                        rec_name = _("[%s] %s - Attendant Staff") % (emp_code, emp.name)
                        rec_amt = 1.0
                        ot_hrs = approved_ot

                    vals_list.append({
                        "name": rec_name,
                        "date": att.check_in,
                        "config_id": cfg.id,
                        "report_type": "extra_hours" if metric_type in ("extra_hours", "unapproved_extra_hours") else metric_type,
                        "amount": rec_amt,
                        "employee_code": emp_code,
                        "check_in": att.check_in,
                        "check_out": att.check_out,
                        "check_in_location_id": location.id or False,
                        "check_in_map_url": (
                            "https://maps.google.com/?q=%s,%s" % (att.in_latitude, att.in_longitude)
                            if att.in_latitude and att.in_longitude else False
                        ),
                        "monthly_wage": wage,
                        "labor_cost_amount": daily_cost,
                        "extra_hours": ot_hrs,
                        "attendant_employee_count": 1,
                        "employee_id": emp.id,
                        "company_id": cfg.company_id.id,
                    })

        created_recs = False
        if vals_list:
            created_recs = self.env["pos.unified.report"].sudo().create(vals_list)

        wizard_vals = {"date_from": period["date_from"], "date_to": period["date_to"]}
        if config_ids:
            wizard_vals["config_ids"] = [(6, 0, list(config_ids))]
        wiz = self.env["pos.unified.report.wizard"].sudo().create(wizard_vals)

        metric_titles = {
            "sales": _("POS Income Transactions"),
            "avg_basket": _("Average Basket: Paying Orders"),
            "untaxed_sales": _("Sales Without Tax Transactions"),
            "tax_amount": _("Sales Tax Transactions"),
            "discount_amount": _("Order Discount Transactions"),
            "gift_amount": _("Gifts (Hospitality) Lines"),
            "expense_amount": _("POS Expenses"),
            "cash_sales": _("Cash Sales Transactions"),
            "visa_sales": _("Visa & Card Sales Transactions"),
            "online_sales": _("Online & Delivery Sales Transactions"),
            "hospitality": _("Hospitality Transactions"),
            "employee_debt": _("Debt Sales (مبيعات الذمم) Transactions"),
            "net_cash_moves": _("Cash Moves (In / Out) Transactions"),
            "cash_in": _("Cash In Transactions"),
            "cash_out": _("Cash Out Transactions"),
            "net_pledges": _("Pledge (Rahen) In / Out Transactions"),
            "rahen_in": _("Pledge (Rahen) In Transactions"),
            "rahen_out": _("Pledge (Rahen) Out Transactions"),
            "advance_deposits": _("Advance Order Deposit Transactions"),
            "pledge_cash": _("Pledge Cash (Received / Returned) Transactions"),
            "pledge_visa": _("Pledge Visa (Received / Returned) Transactions"),
            "advance_cash": _("Advance Cash Deposit Transactions"),
            "advance_visa": _("Advance Visa Deposit Transactions"),
            "attendant_employees": _("Attendant Employees Breakdown"),
            "labor_cost": _("Daily Employee Labor Cost Breakdown"),
            "extra_hours": _("Approved Extra Hours (Overtime) Breakdown"),
            "unapproved_extra_hours": _("Not Approved Extra Hours (Overtime) Breakdown"),
        }
        title = metric_titles.get(metric_type, _("Metric Drill-Down Transactions"))

        domain = [("id", "in", created_recs.ids)] if created_recs else [("id", "=", 0)]

        # Select targeted tree view based on metric_type
        target_tree_xml_id = "anabtawi_pos_reporting_dashboard.view_pos_unified_report_tree"
        if metric_type == "attendant_employees":
            target_tree_xml_id = "anabtawi_pos_reporting_dashboard.view_pos_unified_report_attendance_tree"
        elif metric_type == "labor_cost":
            target_tree_xml_id = "anabtawi_pos_reporting_dashboard.view_pos_unified_report_labor_cost_tree"
        elif metric_type in ("extra_hours", "unapproved_extra_hours"):
            target_tree_xml_id = "anabtawi_pos_reporting_dashboard.view_pos_unified_report_extra_hours_tree"

        tree_view = self.env.ref(target_tree_xml_id, raise_if_not_found=False)
        if not tree_view:
            tree_view = self.env.ref("anabtawi_pos_reporting_dashboard.view_pos_unified_report_tree", raise_if_not_found=False)
        pivot_view = self.env.ref("anabtawi_pos_reporting_dashboard.view_pos_unified_report_pivot", raise_if_not_found=False)
        views = []
        if tree_view:
            views.append((tree_view.id, "list"))
        if pivot_view:
            views.append((pivot_view.id, "pivot"))

        filter_ctx = {
            "attendant_employees": "search_default_filter_attendants",
            "labor_cost": "search_default_filter_labor_cost",
            "extra_hours": "search_default_filter_extra_hours",
            "unapproved_extra_hours": "search_default_filter_extra_hours",
            "pos_sales": "search_default_filter_sales",
            "sales": "search_default_filter_sales",
            "cash_in": "search_default_filter_cash_in",
            "cash_out": "search_default_filter_cash_out",
            "expense_amount": "search_default_filter_expense",
            "rahen_in": "search_default_filter_rahen_in",
            "rahen_out": "search_default_filter_rahen_out",
            "advance_deposits": "search_default_filter_advance",
            "advance_cash": "search_default_filter_advance",
            "advance_visa": "search_default_filter_advance",
        }

        context = {
            "active_wizard_id": wiz.id,
            "metric_type": metric_type,
        }
        if metric_type in filter_ctx:
            context[filter_ctx[metric_type]] = 1

        return {
            "name": title,
            "type": "ir.actions.act_window",
            "res_model": "pos.unified.report",
            "view_mode": "list,pivot,graph",
            "domain": domain,
            "views": views if views else [(False, "list"), (False, "pivot")],
            "target": "current",
            "context": context,
        }

    # -------------------------------------------------------------------------
    # Expenses Dashboard (POS expenses + configured GL accounts)
    # -------------------------------------------------------------------------

    def _get_configured_expense_accounts(self):
        return self.env["pos.expense.dashboard.account"].sudo().search([
            ("active", "=", True),
            ("company_id", "in", self.env.companies.ids),
        ])

    def _account_expense_line_domain(self, account_ids, date_from, date_to):
        return [
            ("account_id", "in", account_ids),
            ("parent_state", "=", "posted"),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
            ("company_id", "in", self.env.companies.ids),
            ("display_type", "not in", ("line_section", "line_subsection", "line_note")),
        ]

    def _get_period_pos_expenses(self, period):
        """All company POS expenses in the period by expense date (no branch filter)."""
        if "pos.expense" not in self.env:
            return self.env["pos.expense"].browse()
        dt_start, dt_end, _, _ = self._period_bounds(period)
        return self.env["pos.expense"].sudo().search([
            ("company_id", "in", self.env.companies.ids),
            ("date", ">=", dt_start),
            ("date", "<=", dt_end),
            ("state", "in", ("to_approve", "approved", "refused")),
        ])

    def _open_period_expense_drilldown(self, period, states=None):
        expenses = self._get_period_pos_expenses(period)
        if states:
            expenses = expenses.filtered(lambda e: e.state in states)
        expense_ids = expenses.ids

        list_view = self.env.ref(
            "anabtawi_pos_expense.view_pos_expense_list", raise_if_not_found=False
        )
        form_view = self.env.ref(
            "anabtawi_pos_expense.view_pos_expense_form", raise_if_not_found=False
        )
        views = []
        if list_view:
            views.append((list_view.id, "list"))
        if form_view:
            views.append((form_view.id, "form"))

        return {
            "name": _("POS Expenses"),
            "type": "ir.actions.act_window",
            "res_model": "pos.expense",
            "view_mode": "list,form",
            "views": views if views else [(False, "list"), (False, "form")],
            "domain": [("id", "in", expense_ids)] if expense_ids else [("id", "=", 0)],
            "target": "current",
            "context": {"create": False, "delete": False},
        }

    @api.model
    def get_expense_dashboard_data(self, date_from=None, date_to=None, config_ids=None):
        """
        Expenses dashboard payload (company totals, no POS branch filter):
        - All POS expenses in the period (by expense date)
        - Totals per configured GL expense account (posted journal items)
        """
        del config_ids  # unused: this dashboard is not branch-scoped
        period = self._parse_period(date_from, date_to)

        # --- POS Expenses (all branches, by expense date) ---
        expense_approved_amount = 0.0
        expense_approved_count = 0
        expense_pending_amount = 0.0
        expense_pending_count = 0

        for expense in self._get_period_pos_expenses(period):
            amt = expense.amount or 0.0
            if expense.state == "approved":
                expense_approved_amount += amt
                expense_approved_count += 1
            else:
                # to_approve + refused
                expense_pending_amount += amt
                expense_pending_count += 1

        # Main POS total = approved + pending (so the card is not stuck at 0 while pending exists)
        expense_amount = expense_approved_amount + expense_pending_amount
        expense_count = expense_approved_count + expense_pending_count

        # --- Configured GL accounts ---
        configured = self._get_configured_expense_accounts()
        account_ids = configured.mapped("account_id").ids
        account_totals = {}
        account_counts = {}
        if account_ids:
            MoveLine = self.env["account.move.line"].sudo()
            domain = self._account_expense_line_domain(
                account_ids, period["date_from"], period["date_to"]
            )
            for account, balance, count in MoveLine._read_group(
                domain,
                ["account_id"],
                ["balance:sum", "__count"],
            ):
                account_totals[account.id] = balance or 0.0
                account_counts[account.id] = count or 0

        account_rows = []
        account_expense_total = 0.0
        account_line_count = 0
        for conf in configured:
            acc = conf.account_id
            amount = account_totals.get(acc.id, 0.0)
            count = account_counts.get(acc.id, 0)
            account_expense_total += amount
            account_line_count += count
            account_rows.append({
                "config_id": conf.id,
                "account_id": acc.id,
                "account_code": conf.account_code or acc.code or "",
                "account_name": conf.account_name or acc.name or "",
                "amount": amount,
                "line_count": count,
            })

        return {
            "date_from": fields.Date.to_string(period["date_from"]),
            "date_to": fields.Date.to_string(period["date_to"]),
            "kpis": {
                "expense_amount": expense_amount,
                "expense_count": expense_count,
                "expense_approved_amount": expense_approved_amount,
                "expense_approved_count": expense_approved_count,
                "expense_pending_amount": expense_pending_amount,
                "expense_pending_count": expense_pending_count,
                "account_expense_total": account_expense_total,
                "account_line_count": account_line_count,
                "account_count": len(account_rows),
                "combined_expense_total": expense_amount + account_expense_total,
            },
            "accounts": account_rows,
        }

    @api.model
    def open_expense_dashboard_pos_drilldown(self, date_from=None, date_to=None):
        """Open all POS expenses in the period (no branch filter)."""
        period = self._parse_period(date_from, date_to)
        return self._open_period_expense_drilldown(period)

    @api.model
    def open_account_expense_drilldown(self, account_id=None, date_from=None, date_to=None):
        """Open posted journal items for one (or all configured) expense account(s)."""
        period = self._parse_period(date_from, date_to)
        configured = self._get_configured_expense_accounts()
        if account_id:
            account_ids = [int(account_id)]
            account = self.env["account.account"].browse(int(account_id))
            title = _("Account Expenses: %s") % (account.display_name or account_id)
        else:
            account_ids = configured.mapped("account_id").ids
            title = _("Configured Account Expenses")

        if not account_ids:
            account_ids = [0]

        domain = self._account_expense_line_domain(
            account_ids, period["date_from"], period["date_to"]
        )
        return {
            "name": title,
            "type": "ir.actions.act_window",
            "res_model": "account.move.line",
            "view_mode": "list,form",
            "views": [(False, "list"), (False, "form")],
            "domain": domain,
            "target": "current",
            "context": {
                "create": False,
                "delete": False,
                "search_default_posted": 1,
            },
        }

