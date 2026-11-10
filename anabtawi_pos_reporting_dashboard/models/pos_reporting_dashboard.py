# -*- coding: utf-8 -*-
import base64
import io
import logging
import math
from collections import defaultdict
from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError
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

    def _accumulate_order_metrics(self, sessions, branch_data, non_product_order_ids=frozenset()):
        """Tax, discounts, gifts and order counts for the period's sessions.

        A range longer than a month is too many payments and lines to walk in
        Python before the worker time limit. The totals below follow the same
        rules as those loops, in three SQL aggregates.

        Untaxed / VAT / channel net / paying orders skip pledge receive/return and
        advance deposit/refund POS orders, cancelled orders, and gift-only orders
        (no non-gift product lines). Total POS Income (``sales``) stays inclusive
        of that money.
        """
        if not sessions:
            return
        session_ids = tuple(sessions.ids)
        excluded = ("hospitality", "advance_applied")
        non_product_orders = tuple(non_product_order_ids) or (0,)
        self.env["pos.payment"].flush_model(["amount", "session_id", "pos_order_id", "payment_method_id"])
        self.env["pos.order"].flush_model(["config_id", "session_id", "state", "amount_total", "amount_tax"])
        self.env["pos.order.line"].flush_model(["order_id", "price_unit", "qty", "discount", "is_gift", "product_id"])
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
               AND (pay.pos_order_id IS NULL OR pay.pos_order_id NOT IN %(non_product_orders)s)
               AND (
                    pay.pos_order_id IS NULL
                    OR (
                        ord.state IN ('paid', 'done', 'invoiced')
                        AND EXISTS (
                            SELECT 1
                              FROM pos_order_line l
                             WHERE l.order_id = ord.id
                               AND COALESCE(l.is_gift, FALSE) IS NOT TRUE
                               AND l.product_id IS NOT NULL
                        )
                    )
               )
             GROUP BY sess.config_id, COALESCE(pm.daily_ops_report_type, 'none')
        """, session_ids=session_ids, excluded=excluded, non_product_orders=non_product_orders))
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
                       AND pay.pos_order_id NOT IN %(non_product_orders)s
                       AND COALESCE(pm.daily_ops_report_type, 'none') NOT IN %(excluded)s
                     GROUP BY pay.pos_order_id
                    HAVING SUM(COALESCE(pay.amount, 0)) > 0.0005
              ) inc ON inc.order_id = ord.id
             WHERE ord.state IN ('paid', 'done', 'invoiced')
               AND EXISTS (
                    SELECT 1
                      FROM pos_order_line l
                     WHERE l.order_id = ord.id
                       AND COALESCE(l.is_gift, FALSE) IS NOT TRUE
                       AND l.product_id IS NOT NULL
               )
             GROUP BY ord.config_id
        """, session_ids=session_ids, excluded=excluded, non_product_orders=non_product_orders))
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

    def _get_paying_orders(self, sessions, non_product_order_ids=None):
        """{pos.order: income} for orders whose income payments are above zero
        (hospitality-only, refund, zero-total gift, pledge and advance orders excluded)."""
        engine = self.env["pos.daily.ops.engine"]
        if non_product_order_ids is None:
            non_product_order_ids = engine._get_non_product_sales_order_ids(sessions)
        order_income = defaultdict(float)
        for pay in engine._get_payments(sessions):
            order = pay.pos_order_id
            if not order or order.id in non_product_order_ids:
                continue
            if engine._is_in_sales(pay.payment_method_id):
                order_income[order] += pay.amount or 0.0
        return {order: income for order, income in order_income.items() if income > 0.0005}

    @staticmethod
    def _avg_basket(values):
        """Average product ticket: cleaned net+VAT over paying product orders."""
        if not values["paying_order_count"]:
            return 0.0
        product_sales = values["untaxed_sales"] + values["tax_amount"]
        return round(product_sales / values["paying_order_count"], 3)

    def _subtract_non_product_channel_payments(self, sessions, branch_data, non_product_order_ids):
        """Remove pledge/advance payments from channel buckets only.

        ``sales`` / Total POS Income stays inclusive of that cash.
        """
        if not sessions or not non_product_order_ids:
            return
        engine = self.env["pos.daily.ops.engine"]
        groups = self.env["pos.payment"].sudo()._read_group(
            [
                ("session_id", "in", sessions.ids),
                ("pos_order_id", "in", list(non_product_order_ids)),
            ],
            ["session_id", "payment_method_id"],
            ["amount:sum"],
        )
        for session, payment_method, amount in groups:
            values = branch_data.get(session.config_id.id)
            if values is None:
                continue
            amount = amount or 0.0
            bucket = engine._get_bucket(payment_method)
            if bucket in ("hospitality", "advance_applied"):
                continue
            key = "other_sales" if bucket == "none" else bucket
            if key in values:
                values[key] -= amount
        for values in branch_data.values():
            values["online_sales"] = sum(values.get(channel, 0.0) for channel in DELIVERY_CHANNELS)

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

    def _open_session_drilldown(self, period, configs):
        """Open the pos.session records the dashboard search included."""
        list_view = self.env.ref("point_of_sale.view_pos_session_tree", raise_if_not_found=False)
        form_view = self.env.ref("point_of_sale.view_pos_session_form", raise_if_not_found=False)
        views = []
        if list_view:
            views.append((list_view.id, "list"))
        if form_view:
            views.append((form_view.id, "form"))
        if configs:
            domain = [
                ("start_at", ">=", period["session_start"]),
                ("start_at", "<=", period["session_end"]),
                ("config_id", "in", configs.ids),
            ]
        else:
            domain = [("id", "=", 0)]
        return {
            "name": _("POS Sessions"),
            "type": "ir.actions.act_window",
            "res_model": "pos.session",
            "view_mode": "list,form",
            "views": views if views else [(False, "list"), (False, "form")],
            "domain": domain,
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
        non_product_order_ids = engine._get_non_product_sales_order_ids(sessions)

        def _empty_branch_dict():
            return {**engine._empty_figures(), **DASHBOARD_EXTRA_KEYS}

        branch_data = defaultdict(_empty_branch_dict)
        for cfg_id, values in figures.items():
            branch_data[cfg_id].update(values)

        # Channel Cash/Visa/… without pledge & advance; Total POS Income (sales) stays full.
        self._subtract_non_product_channel_payments(sessions, branch_data, non_product_order_ids)

        # Tax, discounts, gifts and order counts. Same rules as the old per-record
        # loops, aggregated in SQL so a range longer than a month still returns.
        self._accumulate_order_metrics(sessions, branch_data, non_product_order_ids)

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

        # Daily trends (by business date of the session).
        # total_sales stays inclusive (matches Total POS Income); cash/visa are product-only.
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
            if non_product_order_ids:
                excluded_groups = self.env["pos.payment"].sudo()._read_group(
                    [
                        ("session_id", "in", sessions.ids),
                        ("pos_order_id", "in", list(non_product_order_ids)),
                    ],
                    ["session_id", "payment_method_id"],
                    ["amount:sum"],
                )
                for session, payment_method, amount in excluded_groups:
                    if not engine._is_in_sales(payment_method):
                        continue
                    bucket = engine._get_bucket(payment_method)
                    if bucket not in ("cash", "visa"):
                        continue
                    day = day_totals[engine._to_local_date(session.start_at)]
                    day[bucket] -= amount or 0.0

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
                "session_count": len(sessions),
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

    def _excluded_pos_helper_products(self, configs):
        """Pledge, deposit, employee and delivery products are not stock decisions."""
        Product = self.env["product.product"].sudo()
        excluded = Product.browse()
        if "pledge_product_id" in configs._fields:
            excluded |= configs.mapped("pledge_product_id")
        if "advance_deposit_product_id" in configs._fields:
            excluded |= configs.mapped("advance_deposit_product_id")
        if "pos.site.service.product.line" in self.env:
            lines = self.env["pos.site.service.product.line"].sudo().search([
                ("pledge_product_id", "!=", False),
            ])
            excluded |= lines.mapped("pledge_product_id")
        helper_domain = []
        if "is_employee_service" in Product._fields and "is_delivery_product" in Product._fields:
            helper_domain = ["|", ("is_employee_service", "=", True), ("is_delivery_product", "=", True)]
        if "pledge_amount" in Product._fields:
            helper_domain = (["|"] + helper_domain + [("pledge_amount", ">", 0)]) if helper_domain else [("pledge_amount", ">", 0)]
        if helper_domain:
            excluded |= Product.search(helper_domain)
        return excluded

    def _pos_menu_products(self, configs):
        """Products the selected POS configs can actually sell.

        This is the Point of Sale menu, not the whole product catalog. A product
        with no sales in the period stays in the list.
        """
        Product = self.env["product.product"].sudo()
        if not configs:
            return Product.browse()
        domain = [
            ("available_in_pos", "=", True),
            ("sale_ok", "=", True),
            ("active", "=", True),
            "|",
            ("company_id", "=", False),
            ("company_id", "in", configs.company_id.ids),
        ]
        limited = configs.filtered("limit_categories")
        if limited and len(limited) == len(configs):
            categ_ids = limited.iface_available_categ_ids.ids
            if not categ_ids:
                return Product.browse()
            domain.append(("pos_categ_ids", "in", categ_ids))
        products = Product.search(domain)
        return products - self._excluded_pos_helper_products(configs)

    def _config_stock_location(self, config):
        """Stock location this POS sells from. Child locations are included later."""
        if "stock.location" not in self.env:
            return False
        Location = self.env["stock.location"]
        picking = config.picking_type_id if "picking_type_id" in config._fields else Location.browse()
        if picking and picking.default_location_src_id:
            return picking.default_location_src_id
        warehouse = config.warehouse_id if "warehouse_id" in config._fields else Location.browse()
        if warehouse and warehouse.lot_stock_id:
            return warehouse.lot_stock_id
        return Location.browse()

    def _config_transfer_stock_location(self, config):
        """Stock location for the Transfers dashboard (explicit mapping preferred)."""
        if "pos.dashboard.transfer.location" in self.env:
            mapping = self.env["pos.dashboard.transfer.location"].sudo().search(
                [("config_id", "=", config.id), ("active", "=", True)],
                limit=1,
            )
            if mapping.location_id:
                return mapping.location_id
        return self._config_stock_location(config)

    def _products_available_in_period(self, products, locations, period):
        """{(product_id, location_id)} on hand above zero on any day of the period.

        This is the Inventory at Date quantity for the POS stock location and
        its children. The check runs from the start of the first day through
        the end of the last day. A receipt or a balance already above zero
        counts. Ending the period at zero still counts when the shelf was
        above zero earlier.
        """
        product_ids = tuple(products.ids)
        root_ids = tuple(location.id for location in locations if location)
        if not product_ids or not root_ids or "stock.quant" not in self.env:
            return set()
        self.env["stock.quant"].flush_model(["product_id", "location_id", "quantity"])
        self.env["stock.move.line"].flush_model([
            "product_id", "location_id", "location_dest_id", "quantity_product_uom", "date", "state",
        ])
        self.env["stock.location"].flush_model(["location_id"])
        self.env.cr.execute(SQL("""
            WITH RECURSIVE descendants AS (
                SELECT id AS child_id, id AS root_id
                  FROM stock_location
                 WHERE id IN %(root_ids)s
                UNION
                SELECT sl.id, d.root_id
                  FROM stock_location sl
                  JOIN descendants d ON sl.location_id = d.child_id
            ),
            on_hand_now AS (
                SELECT q.product_id, d.root_id, COALESCE(SUM(q.quantity), 0) AS qty
                  FROM stock_quant q
                  JOIN descendants d ON d.child_id = q.location_id
                 WHERE q.product_id IN %(product_ids)s
                 GROUP BY q.product_id, d.root_id
            ),
            signed AS (
                SELECT sml.product_id, d.root_id, sml.date, sml.id, sml.quantity_product_uom AS qty
                  FROM stock_move_line sml
                  JOIN descendants d ON d.child_id = sml.location_dest_id
                 WHERE sml.state = 'done'
                   AND sml.date >= %(start)s
                   AND sml.product_id IN %(product_ids)s
                UNION ALL
                SELECT sml.product_id, d.root_id, sml.date, sml.id, -sml.quantity_product_uom
                  FROM stock_move_line sml
                  JOIN descendants d ON d.child_id = sml.location_id
                 WHERE sml.state = 'done'
                   AND sml.date >= %(start)s
                   AND sml.product_id IN %(product_ids)s
            ),
            net_move AS (
                SELECT product_id, root_id, date, id, SUM(qty) AS delta
                  FROM signed
                 GROUP BY product_id, root_id, date, id
            ),
            qty_at_start AS (
                SELECT product_id, root_id, qty
                  FROM (
                        SELECT COALESCE(n.product_id, m.product_id) AS product_id,
                               COALESCE(n.root_id, m.root_id) AS root_id,
                               COALESCE(n.qty, 0) - COALESCE(m.qty, 0) AS qty
                          FROM on_hand_now n
                          FULL JOIN (
                                SELECT product_id, root_id, SUM(delta) AS qty
                                  FROM net_move
                                 GROUP BY product_id, root_id
                          ) m ON m.product_id = n.product_id AND m.root_id = n.root_id
                  ) start_qty
            ),
            running AS (
                SELECT mv.product_id,
                       mv.root_id,
                       COALESCE(st.qty, 0) + SUM(mv.delta) OVER (
                           PARTITION BY mv.product_id, mv.root_id
                           ORDER BY mv.date, mv.id
                       ) AS qty
                  FROM net_move mv
                  LEFT JOIN qty_at_start st
                    ON st.product_id = mv.product_id AND st.root_id = mv.root_id
                 WHERE mv.date <= %(end)s
            )
            SELECT product_id, root_id
              FROM qty_at_start
             WHERE qty > 0.0000001
            UNION
            SELECT product_id, root_id
              FROM running
             WHERE qty > 0.0000001
        """, product_ids=product_ids, root_ids=root_ids, start=period["session_start"], end=period["session_end"]))
        return {(product_id, location_id) for product_id, location_id in self.env.cr.fetchall()}

    def _products_in_stock_now(self, products, locations):
        """{(product_id, location_id)} whose on-hand quantity is above zero today."""
        product_ids = tuple(products.ids)
        root_ids = tuple(location.id for location in locations if location)
        if not product_ids or not root_ids or "stock.quant" not in self.env:
            return set()
        self.env["stock.quant"].flush_model(["product_id", "location_id", "quantity"])
        self.env["stock.location"].flush_model(["location_id"])
        self.env.cr.execute(SQL("""
            WITH RECURSIVE descendants AS (
                SELECT id AS child_id, id AS root_id
                  FROM stock_location
                 WHERE id IN %(root_ids)s
                UNION
                SELECT sl.id, d.root_id
                  FROM stock_location sl
                  JOIN descendants d ON sl.location_id = d.child_id
            )
            SELECT q.product_id, d.root_id
              FROM stock_quant q
              JOIN descendants d ON d.child_id = q.location_id
             WHERE q.product_id IN %(product_ids)s
             GROUP BY q.product_id, d.root_id
            HAVING SUM(q.quantity) > 0.0000001
        """, product_ids=product_ids, root_ids=root_ids))
        return {(product_id, location_id) for product_id, location_id in self.env.cr.fetchall()}

    def _product_sales_stats(self, sessions, exclude_order_ids=None):
        """{(product_id, config_id): stats} for paid lines, gifts excluded.

        A line that already has ``total_cost`` keeps that cost. A line that
        does not uses the product's current Cost (``standard_price``) times
        the quantity, converted into the order currency.

        ``exclude_order_ids`` skips pledge/advance (non-product) orders when set.
        """
        if not sessions:
            return {}
        excluded = tuple(oid for oid in (exclude_order_ids or ()) if oid) or (0,)
        self.env["pos.order.line"].flush_model([
            "product_id", "qty", "price_subtotal", "total_cost", "is_total_cost_computed", "order_id", "is_gift",
        ])
        self.env["pos.order"].flush_model(["session_id", "state", "company_id", "currency_rate"])
        self.env["pos.session"].flush_model(["config_id"])
        self.env["product.product"].flush_model(["standard_price"])
        self.env.cr.execute(SQL("""
            SELECT line.product_id,
                   sess.config_id,
                   COALESCE(SUM(line.qty), 0) AS qty,
                   COALESCE(SUM(line.price_subtotal), 0) AS sales,
                   COALESCE(SUM(
                       CASE
                           WHEN line.is_total_cost_computed THEN line.total_cost
                           ELSE line.qty
                                * COALESCE((pp.standard_price ->> (ord.company_id::varchar))::numeric, 0)
                                * COALESCE(NULLIF(ord.currency_rate, 0), 1)
                       END
                   ), 0) AS cost,
                   COUNT(DISTINCT line.order_id) AS order_count
              FROM pos_order_line line
              JOIN pos_order ord ON ord.id = line.order_id
              JOIN pos_session sess ON sess.id = ord.session_id
              JOIN product_product pp ON pp.id = line.product_id
             WHERE ord.session_id IN %(session_ids)s
               AND ord.state IN ('paid', 'done', 'invoiced')
               AND line.product_id IS NOT NULL
               AND sess.config_id IS NOT NULL
               AND COALESCE(line.is_gift, FALSE) IS NOT TRUE
               AND ord.id NOT IN %(excluded_orders)s
             GROUP BY line.product_id, sess.config_id
        """, session_ids=tuple(sessions.ids), excluded_orders=excluded))
        stats = {}
        for product_id, config_id, qty, sales, cost, order_count in self.env.cr.fetchall():
            stats[(product_id, config_id)] = {
                "qty": float(qty or 0.0),
                "sales": float(sales or 0.0),
                "cost": float(cost or 0.0),
                "order_count": int(order_count or 0),
            }
        return stats

    def _product_compare_sales_stats(self, sessions, exclude_order_ids=None):
        """Product sales for Compare, aligned with Branches Sales Without Tax rules.

        - Untaxed line ``price_subtotal`` (no tax)
        - Gift / hospitality lines excluded
        - Pledge / advance orders excluded via ``exclude_order_ids``
        - Orders paid only with hospitality payment methods excluded
        - Orders with no normal (Cash/Visa/…) payment excluded
        - Refunds: if normal payments on the order are negative, qty/sales are signed negative
        """
        if not sessions:
            return {}
        excluded = tuple(oid for oid in (exclude_order_ids or ()) if oid) or (0,)
        self.env["pos.order.line"].flush_model([
            "product_id", "qty", "price_subtotal", "total_cost", "is_total_cost_computed", "order_id", "is_gift",
        ])
        self.env["pos.order"].flush_model(["session_id", "state", "company_id", "currency_rate"])
        self.env["pos.session"].flush_model(["config_id"])
        self.env["pos.payment"].flush_model(["amount", "session_id", "pos_order_id", "payment_method_id"])
        self.env["pos.payment.method"].flush_model(["daily_ops_report_type"])
        self.env["product.product"].flush_model(["standard_price"])
        self.env.cr.execute(SQL("""
            WITH normal_pay AS (
                SELECT pay.pos_order_id AS order_id,
                       SUM(COALESCE(pay.amount, 0)) AS pay_total
                  FROM pos_payment pay
                  LEFT JOIN pos_payment_method pm ON pm.id = pay.payment_method_id
                 WHERE pay.session_id IN %(session_ids)s
                   AND pay.pos_order_id IS NOT NULL
                   AND COALESCE(pm.daily_ops_report_type, 'none') NOT IN ('hospitality', 'advance_applied')
                 GROUP BY pay.pos_order_id
                HAVING ABS(SUM(COALESCE(pay.amount, 0))) > 0.0005
            )
            SELECT line.product_id,
                   sess.config_id,
                   COALESCE(SUM(
                       CASE
                           WHEN np.pay_total < 0 THEN -ABS(COALESCE(line.qty, 0))
                           ELSE COALESCE(line.qty, 0)
                       END
                   ), 0) AS qty,
                   COALESCE(SUM(
                       CASE
                           WHEN np.pay_total < 0 THEN -ABS(COALESCE(line.price_subtotal, 0))
                           ELSE COALESCE(line.price_subtotal, 0)
                       END
                   ), 0) AS sales,
                   COALESCE(SUM(
                       CASE
                           WHEN line.is_total_cost_computed THEN
                               CASE
                                   WHEN np.pay_total < 0 THEN -ABS(COALESCE(line.total_cost, 0))
                                   ELSE COALESCE(line.total_cost, 0)
                               END
                           ELSE
                               CASE
                                   WHEN np.pay_total < 0 THEN -ABS(COALESCE(line.qty, 0))
                                   ELSE COALESCE(line.qty, 0)
                               END
                               * COALESCE((pp.standard_price ->> (ord.company_id::varchar))::numeric, 0)
                               * COALESCE(NULLIF(ord.currency_rate, 0), 1)
                       END
                   ), 0) AS cost,
                   COUNT(DISTINCT line.order_id) AS order_count
              FROM pos_order_line line
              JOIN pos_order ord ON ord.id = line.order_id
              JOIN pos_session sess ON sess.id = ord.session_id
              JOIN product_product pp ON pp.id = line.product_id
              JOIN normal_pay np ON np.order_id = ord.id
             WHERE ord.session_id IN %(session_ids)s
               AND ord.state IN ('paid', 'done', 'invoiced')
               AND line.product_id IS NOT NULL
               AND sess.config_id IS NOT NULL
               AND COALESCE(line.is_gift, FALSE) IS NOT TRUE
               AND ord.id NOT IN %(excluded_orders)s
             GROUP BY line.product_id, sess.config_id
        """, session_ids=tuple(sessions.ids), excluded_orders=excluded))
        stats = {}
        for product_id, config_id, qty, sales, cost, order_count in self.env.cr.fetchall():
            stats[(product_id, config_id)] = {
                "qty": float(qty or 0.0),
                "sales": float(sales or 0.0),
                "cost": float(cost or 0.0),
                "order_count": int(order_count or 0),
            }
        return stats

    @staticmethod
    def _compare_delta(current, previous):
        """Amount and percent change from previous → current."""
        current = float(current or 0.0)
        previous = float(previous or 0.0)
        amount = round(current - previous, 3)
        if abs(previous) < 0.0005:
            percent = 100.0 if abs(current) > 0.0005 else 0.0
        else:
            percent = round((amount / previous) * 100.0, 1)
        if amount > 0.0005:
            direction = "up"
        elif amount < -0.0005:
            direction = "down"
        else:
            direction = "flat"
        return {
            "amount": amount,
            "percent": percent,
            "direction": direction,
        }

    @api.model
    def get_compare_dashboard_data(
        self,
        date_from_a=None,
        date_to_a=None,
        date_from_b=None,
        date_to_b=None,
        config_ids=None,
        product_id=None,
    ):
        """Compare real product sales (untaxed, no hospitality) between two periods."""
        self._check_product_dashboard_access()
        engine = self.env["pos.daily.ops.engine"]
        period_a = self._parse_period(date_from_a, date_to_a)
        period_b = self._parse_period(date_from_b, date_to_b)
        configs = self._get_report_configs(config_ids)
        all_configs = self._get_report_configs()

        sessions_a = engine._get_sessions(period_a, configs)
        sessions_b = engine._get_sessions(period_b, configs)
        exclude_a = engine._get_non_product_sales_order_ids(sessions_a)
        exclude_b = engine._get_non_product_sales_order_ids(sessions_b)
        stats_a = self._product_compare_sales_stats(sessions_a, exclude_order_ids=exclude_a)
        stats_b = self._product_compare_sales_stats(sessions_b, exclude_order_ids=exclude_b)

        product_filter_id = int(product_id) if product_id else False
        keys = set(stats_a) | set(stats_b)
        if product_filter_id:
            keys = {key for key in keys if key[0] == product_filter_id}

        product_ids = {key[0] for key in keys}
        products = {
            product.id: product
            for product in self.env["product.product"].sudo().browse(list(product_ids))
        }
        config_names = {config.id: config.name for config in configs}

        rows = []
        for product_id_key, config_id in keys:
            product = products.get(product_id_key)
            if not product:
                continue
            a = stats_a.get((product_id_key, config_id), {})
            b = stats_b.get((product_id_key, config_id), {})
            sales_a = float(a.get("sales") or 0.0)
            sales_b = float(b.get("sales") or 0.0)
            qty_a = float(a.get("qty") or 0.0)
            qty_b = float(b.get("qty") or 0.0)
            orders_a = int(a.get("order_count") or 0)
            orders_b = int(b.get("order_count") or 0)
            # Δ = Period B − Period A (B is the focus period).
            sales_delta = self._compare_delta(sales_b, sales_a)
            qty_delta = self._compare_delta(qty_b, qty_a)
            orders_delta = self._compare_delta(orders_b, orders_a)
            rows.append({
                "row_key": "%s-%s" % (product_id_key, config_id),
                "product_id": product_id_key,
                "config_id": config_id,
                "product_name": product.display_name,
                "branch_name": config_names.get(config_id) or "",
                "sales_a": round(sales_a, 3),
                "sales_b": round(sales_b, 3),
                "sales_delta": sales_delta["amount"],
                "sales_delta_pct": sales_delta["percent"],
                "sales_direction": sales_delta["direction"],
                "qty_a": round(qty_a, 3),
                "qty_b": round(qty_b, 3),
                "qty_delta": qty_delta["amount"],
                "qty_delta_pct": qty_delta["percent"],
                "qty_direction": qty_delta["direction"],
                "orders_a": orders_a,
                "orders_b": orders_b,
                "orders_delta": orders_delta["amount"],
                "orders_delta_pct": orders_delta["percent"],
                "orders_direction": orders_delta["direction"],
            })

        rows.sort(key=lambda r: (r["sales_delta"], r["product_name"], r["branch_name"]))

        def _sum(field):
            return round(sum(r[field] for r in rows), 3)

        summary = {
            "row_count": len(rows),
            "sales_a": _sum("sales_a"),
            "sales_b": _sum("sales_b"),
            "qty_a": _sum("qty_a"),
            "qty_b": _sum("qty_b"),
            "orders_a": int(sum(r["orders_a"] for r in rows)),
            "orders_b": int(sum(r["orders_b"] for r in rows)),
        }
        summary["sales_delta"] = self._compare_delta(summary["sales_b"], summary["sales_a"])
        summary["qty_delta"] = self._compare_delta(summary["qty_b"], summary["qty_a"])
        summary["orders_delta"] = self._compare_delta(summary["orders_b"], summary["orders_a"])

        return {
            "date_from_a": period_a["date_from"].isoformat(),
            "date_to_a": period_a["date_to"].isoformat(),
            "date_from_b": period_b["date_from"].isoformat(),
            "date_to_b": period_b["date_to"].isoformat(),
            "all_branches": [{"id": c.id, "name": c.name} for c in all_configs],
            "product_id": product_filter_id or False,
            "product_name": (
                self.env["product.product"].sudo().browse(product_filter_id).display_name
                if product_filter_id else ""
            ),
            "summary": summary,
            "rows": rows,
            "error": "",
        }

    @api.model
    def search_compare_products(self, term="", limit=30):
        """Product autocomplete for the Compare tab."""
        self._check_product_dashboard_access()
        term = (term or "").strip()
        Product = self.env["product.product"].sudo()
        domain = [("available_in_pos", "=", True), ("sale_ok", "=", True), ("active", "=", True)]
        if term:
            domain = ["&"] + domain + [
                "|", "|",
                ("name", "ilike", term),
                ("default_code", "ilike", term),
                ("barcode", "ilike", term),
            ]
        products = Product.search(domain, limit=max(1, min(int(limit or 30), 80)), order="default_code, name, id")
        return [{"id": p.id, "name": p.display_name} for p in products]

    @api.model
    def _generate_compare_xlsx(self, rows, summary, period_a_label, period_b_label):
        import xlsxwriter

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet(_("Sales compare"))

        title_fmt = workbook.add_format({"bold": True, "font_size": 14, "font_color": "#1A252C"})
        sub_fmt = workbook.add_format({"font_size": 10, "font_color": "#555555"})
        header_fmt = workbook.add_format({
            "bold": True,
            "bg_color": "#1F4E78",
            "font_color": "#FFFFFF",
            "border": 1,
            "align": "center",
            "valign": "vcenter",
        })
        text_fmt = workbook.add_format({"border": 1, "align": "left"})
        num_fmt = workbook.add_format({"border": 1, "num_format": "#,##0.000", "align": "right"})
        int_fmt = workbook.add_format({"border": 1, "num_format": "#,##0", "align": "right"})
        pct_fmt = workbook.add_format({"border": 1, "num_format": '0.0"%"', "align": "right"})
        # Whole-number % like the sample: %-18 / %38
        pct_whole_fmt = workbook.add_format({
            "border": 1, "num_format": '"%"0;"%"-0;"%"0', "align": "right",
        })
        pct_whole_up_fmt = workbook.add_format({
            "border": 1, "num_format": '"%"0;"%"-0;"%"0', "align": "right", "font_color": "#15803D",
        })
        pct_whole_down_fmt = workbook.add_format({
            "border": 1, "num_format": '"%"0;"%"-0;"%"0', "align": "right", "font_color": "#B91C1C",
        })
        up_fmt = workbook.add_format({
            "border": 1, "num_format": "#,##0.000", "align": "right", "font_color": "#15803D", "bold": True,
        })
        down_fmt = workbook.add_format({
            "border": 1, "num_format": "#,##0.000", "align": "right", "font_color": "#B91C1C", "bold": True,
        })
        flat_fmt = workbook.add_format({
            "border": 1, "num_format": "#,##0.000", "align": "right", "font_color": "#64748B",
        })

        sheet.write(0, 0, _("Product sales comparison"), title_fmt)
        sheet.write(1, 0, _("Period A: %s") % period_a_label, sub_fmt)
        sheet.write(2, 0, _("Period B: %s") % period_b_label, sub_fmt)
        sheet.write(
            3,
            0,
            _("Untaxed product sales only (hospitality / gift and pledge-advance orders excluded)."),
            sub_fmt,
        )

        summary = summary or {}
        sheet.write(5, 0, _("Summary"), workbook.add_format({"bold": True}))
        sheet.write(6, 0, _("Sales A"), text_fmt)
        sheet.write_number(6, 1, float(summary.get("sales_a") or 0.0), num_fmt)
        sheet.write(6, 2, _("Sales B"), text_fmt)
        sheet.write_number(6, 3, float(summary.get("sales_b") or 0.0), num_fmt)
        sales_delta = (summary.get("sales_delta") or {}).get("amount", 0.0)
        sheet.write(6, 4, _("Sales change"), text_fmt)
        sheet.write_number(6, 5, float(sales_delta), num_fmt)

        headers = [
            _("Product"),
            _("Branch"),
            _("Sales A"),
            _("Sales B"),
            _("Sales Δ"),
            _("Sales Δ %"),
            _("Qty A"),
            _("Qty B"),
            _("Qty Δ"),
            _("Qty Δ %"),
            _("Orders A"),
            _("Orders B"),
            _("Orders Δ"),
            _("Orders Δ %"),
            _("Sales trend"),
        ]
        header_row = 8
        for col, label in enumerate(headers):
            sheet.write(header_row, col, label, header_fmt)

        def _delta_fmt(direction):
            if direction == "up":
                return up_fmt
            if direction == "down":
                return down_fmt
            return flat_fmt

        def _pct_whole_fmt(direction):
            if direction == "up":
                return pct_whole_up_fmt
            if direction == "down":
                return pct_whole_down_fmt
            return pct_whole_fmt

        def _pct_whole(value):
            return int(round(float(value or 0.0)))

        for row_idx, row in enumerate(rows, start=header_row + 1):
            sheet.write(row_idx, 0, row.get("product_name") or "", text_fmt)
            sheet.write(row_idx, 1, row.get("branch_name") or "", text_fmt)
            sheet.write_number(row_idx, 2, float(row.get("sales_a") or 0.0), num_fmt)
            sheet.write_number(row_idx, 3, float(row.get("sales_b") or 0.0), num_fmt)
            sheet.write_number(row_idx, 4, float(row.get("sales_delta") or 0.0), _delta_fmt(row.get("sales_direction")))
            sheet.write_number(row_idx, 5, _pct_whole(row.get("sales_delta_pct")), _pct_whole_fmt(row.get("sales_direction")))
            sheet.write_number(row_idx, 6, float(row.get("qty_a") or 0.0), num_fmt)
            sheet.write_number(row_idx, 7, float(row.get("qty_b") or 0.0), num_fmt)
            sheet.write_number(row_idx, 8, float(row.get("qty_delta") or 0.0), _delta_fmt(row.get("qty_direction")))
            sheet.write_number(row_idx, 9, _pct_whole(row.get("qty_delta_pct")), _pct_whole_fmt(row.get("qty_direction")))
            sheet.write_number(row_idx, 10, int(row.get("orders_a") or 0), int_fmt)
            sheet.write_number(row_idx, 11, int(row.get("orders_b") or 0), int_fmt)
            sheet.write_number(row_idx, 12, float(row.get("orders_delta") or 0.0), _delta_fmt(row.get("orders_direction")))
            sheet.write_number(row_idx, 13, _pct_whole(row.get("orders_delta_pct")), _pct_whole_fmt(row.get("orders_direction")))
            trend = {"up": _("Increase"), "down": _("Decrease"), "flat": _("No change")}.get(
                row.get("sales_direction"), _("No change")
            )
            sheet.write(row_idx, 14, trend, text_fmt)

        sheet.set_column(0, 0, 42)
        sheet.set_column(1, 1, 24)
        sheet.set_column(2, 13, 12)
        sheet.set_column(14, 14, 12)
        sheet.freeze_panes(header_row + 1, 0)

        # --- Sheet 2: Sales Comparison per Branch ---
        branch_sheet = workbook.add_worksheet(_("Sales Comparison per Branch"))
        branch_sheet.write(0, 0, _("Sales Comparison per Branch"), title_fmt)
        branch_sheet.write(1, 0, _("Period A: %s") % period_a_label, sub_fmt)
        branch_sheet.write(2, 0, _("Period B: %s") % period_b_label, sub_fmt)
        branch_headers = [
            _("Branch"),
            _("Period A Sales"),
            _("Period B Sales"),
            _("Diff."),
            _("%"),
        ]
        for col, label in enumerate(branch_headers):
            branch_sheet.write(4, col, label, header_fmt)

        branch_totals = defaultdict(lambda: {"sales_a": 0.0, "sales_b": 0.0})
        for row in rows:
            name = row.get("branch_name") or _("Unknown")
            branch_totals[name]["sales_a"] += float(row.get("sales_a") or 0.0)
            branch_totals[name]["sales_b"] += float(row.get("sales_b") or 0.0)

        branch_rows = []
        for name in sorted(branch_totals.keys()):
            sales_a = round(branch_totals[name]["sales_a"], 3)
            sales_b = round(branch_totals[name]["sales_b"], 3)
            delta = self._compare_delta(sales_b, sales_a)
            branch_rows.append((name, sales_a, sales_b, delta))

        total_a = 0.0
        total_b = 0.0
        for idx, (name, sales_a, sales_b, delta) in enumerate(branch_rows):
            r = 5 + idx
            total_a += sales_a
            total_b += sales_b
            branch_sheet.write(r, 0, name, text_fmt)
            branch_sheet.write_number(r, 1, sales_a, num_fmt)
            branch_sheet.write_number(r, 2, sales_b, num_fmt)
            branch_sheet.write_number(r, 3, float(delta["amount"]), _delta_fmt(delta["direction"]))
            branch_sheet.write_number(r, 4, _pct_whole(delta["percent"]), _pct_whole_fmt(delta["direction"]))

        total_row = 5 + len(branch_rows)
        total_fmt = workbook.add_format({
            "bold": True, "border": 1, "num_format": "#,##0.000", "align": "right", "bg_color": "#E8EEF4",
        })
        total_text_fmt = workbook.add_format({
            "bold": True, "border": 1, "align": "left", "bg_color": "#E8EEF4",
        })
        total_pct_fmt = workbook.add_format({
            "bold": True, "border": 1, "num_format": '"%"0;"%"-0;"%"0', "align": "right", "bg_color": "#E8EEF4",
        })
        total_delta = self._compare_delta(total_b, total_a)
        branch_sheet.write(total_row, 0, _("Total"), total_text_fmt)
        branch_sheet.write_number(total_row, 1, round(total_a, 3), total_fmt)
        branch_sheet.write_number(total_row, 2, round(total_b, 3), total_fmt)
        branch_sheet.write_number(total_row, 3, float(total_delta["amount"]), total_fmt)
        branch_sheet.write_number(total_row, 4, _pct_whole(total_delta["percent"]), total_pct_fmt)
        branch_sheet.set_column(0, 0, 28)
        branch_sheet.set_column(1, 4, 16)
        branch_sheet.freeze_panes(5, 0)

        # --- Sheet 3: Sales Comparison per Product (all selected branches) ---
        product_sheet = workbook.add_worksheet(_("Sales Comparison per Product"))
        product_sheet.write(0, 0, _("Sales Comparison per Product"), title_fmt)
        product_sheet.write(1, 0, _("Period A: %s") % period_a_label, sub_fmt)
        product_sheet.write(2, 0, _("Period B: %s") % period_b_label, sub_fmt)
        product_sheet.write(3, 0, _("Scope ALL = selected branches combined per product."), sub_fmt)
        product_headers = [
            _("Scope"),
            _("Product"),
            _("Period A Sale"),
            _("Period B Sale"),
            _("Diff."),
            _("%"),
        ]
        for col, label in enumerate(product_headers):
            product_sheet.write(5, col, label, header_fmt)

        product_totals = {}
        for row in rows:
            product_id = row.get("product_id") or 0
            bucket = product_totals.setdefault(product_id, {
                "name": row.get("product_name") or "",
                "sales_a": 0.0,
                "sales_b": 0.0,
            })
            bucket["sales_a"] += float(row.get("sales_a") or 0.0)
            bucket["sales_b"] += float(row.get("sales_b") or 0.0)

        product_rows = []
        for product_id, bucket in product_totals.items():
            sales_a = round(bucket["sales_a"], 3)
            sales_b = round(bucket["sales_b"], 3)
            delta = self._compare_delta(sales_b, sales_a)
            product_rows.append((bucket["name"], sales_a, sales_b, delta))
        product_rows.sort(key=lambda item: (item[0] or "").lower())

        for idx, (name, sales_a, sales_b, delta) in enumerate(product_rows):
            r = 6 + idx
            product_sheet.write(r, 0, _("ALL"), text_fmt)
            product_sheet.write(r, 1, name, text_fmt)
            product_sheet.write_number(r, 2, sales_a, num_fmt)
            product_sheet.write_number(r, 3, sales_b, num_fmt)
            product_sheet.write_number(r, 4, float(delta["amount"]), _delta_fmt(delta["direction"]))
            product_sheet.write_number(r, 5, _pct_whole(delta["percent"]), _pct_whole_fmt(delta["direction"]))

        product_sheet.set_column(0, 0, 10)
        product_sheet.set_column(1, 1, 42)
        product_sheet.set_column(2, 5, 16)
        product_sheet.freeze_panes(6, 0)

        workbook.close()
        return output.getvalue()

    @api.model
    def action_export_compare_xlsx(
        self,
        date_from_a=None,
        date_to_a=None,
        date_from_b=None,
        date_to_b=None,
        config_ids=None,
        product_id=None,
        sort_key="sales_delta",
        sort_order="asc",
        search="",
    ):
        """Download the Compare tab table as Excel."""
        self._check_product_dashboard_access()
        data = self.get_compare_dashboard_data(
            date_from_a=date_from_a,
            date_to_a=date_to_a,
            date_from_b=date_from_b,
            date_to_b=date_to_b,
            config_ids=config_ids,
            product_id=product_id,
        )
        rows = list(data.get("rows") or [])
        query = (search or "").strip().lower()
        if query:
            rows = [
                row for row in rows
                if query in (row.get("product_name") or "").lower()
                or query in (row.get("branch_name") or "").lower()
            ]
        reverse = (sort_order or "asc") == "desc"
        key = sort_key or "sales_delta"

        def _sort_value(row):
            value = row.get(key)
            if isinstance(value, str):
                return (value or "").lower()
            return value if value is not None else 0

        rows.sort(key=_sort_value, reverse=reverse)
        period_a_label = "%s → %s" % (data.get("date_from_a") or "", data.get("date_to_a") or "")
        period_b_label = "%s → %s" % (data.get("date_from_b") or "", data.get("date_to_b") or "")
        content = self._generate_compare_xlsx(rows, data.get("summary") or {}, period_a_label, period_b_label)
        filename = "POS_Sales_Compare_%s_%s_vs_%s_%s.xlsx" % (
            data.get("date_from_a") or "a_from",
            data.get("date_to_a") or "a_to",
            data.get("date_from_b") or "b_from",
            data.get("date_to_b") or "b_to",
        )
        attachment = self.env["ir.attachment"].sudo().create(
            {
                "name": filename,
                "type": "binary",
                "datas": base64.b64encode(content),
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "res_model": "pos.reporting.dashboard",
                "res_id": 0,
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    @staticmethod
    def _product_decision(row, top_qty_ids, avg_margin):
        margin = row["margin"]
        if row["product_id"] in top_qty_ids and margin is not None and avg_margin > 0 and margin < avg_margin * 0.6:
            return "review_price"
        if row["product_id"] in top_qty_ids and margin is not None and margin >= avg_margin:
            return "stock_more"
        return "keep"

    def _check_product_dashboard_access(self):
        if not self.env.user.has_group("anabtawi_pos_reporting_dashboard.group_pos_dashboard_products"):
            raise AccessError(_("You are not allowed to view the product section of the POS dashboard."))

    @api.model
    def get_product_dashboard_data(self, date_from=None, date_to=None, config_ids=None):
        """One row per POS-menu product and branch.

        Did not sell means the product was on hand at that branch on a day in the
        period and still sold nothing there. A branch that never had it on
        the shelf is "Not in this branch", including when the sold quantity
        is zero. Sales still count when the shelf is empty now.
        """
        self._check_product_dashboard_access()
        engine = self.env["pos.daily.ops.engine"]
        period = self._parse_period(date_from, date_to)
        configs = self._get_report_configs(config_ids)
        sessions = engine._get_sessions(period, configs)
        menus = {config.id: self._pos_menu_products(config) for config in configs}
        products = self.env["product.product"].browse()
        for menu in menus.values():
            products |= menu
        locations = {config.id: self._config_stock_location(config) for config in configs}
        stock_locations = [location for location in locations.values() if location]
        available = self._products_available_in_period(products, stock_locations, period)
        in_stock_now = self._products_in_stock_now(products, stock_locations)
        stats = self._product_sales_stats(
            sessions,
            exclude_order_ids=engine._get_non_product_sales_order_ids(sessions),
        )
        rates = {
            rate.pos_categ_id.id: rate.percentage
            for rate in self.env["pos.category.profit.rate"].sudo().search([])
            if rate.pos_categ_id
        }

        rows = []
        for config in configs:
            location = locations.get(config.id)
            stock_known = bool(location)
            for product in menus.get(config.id, self.env["product.product"]):
                stat = stats.get((product.id, config.id), {})
                qty = stat.get("qty", 0.0)
                sales = stat.get("sales", 0.0)
                cost = stat.get("cost", 0.0)
                sold = bool(stat)
                profit = (sales - cost) if sold else None
                margin = ((sales - cost) / sales) if sold and sales else None
                category = product.pos_categ_ids[:1]
                on_shelf = stock_known and (product.id, location.id) in available
                in_stock = stock_known and (product.id, location.id) in in_stock_now
                percentage = rates.get(category.id) if category else None
                # With a rate: sales − cost × %/100. Without a rate: sales − full cost.
                if percentage is not None:
                    category_profit = sales - cost * (percentage / 100.0)
                else:
                    category_profit = sales - cost
                rows.append({
                    "row_key": "%s-%s" % (config.id, product.id),
                    "product_id": product.id,
                    "config_id": config.id,
                    "branch_name": config.name,
                    "name": product.display_name,
                    "category": category.display_name if category else _("No POS category"),
                    "qty": round(qty, 3),
                    "sales": round(sales, 3),
                    "cost": round(cost, 3) if sold else None,
                    "profit": round(profit, 3) if profit is not None else None,
                    "margin": round(margin * 100.0, 1) if margin is not None else None,
                    "percentage": round(percentage, 2) if percentage is not None else None,
                    "category_profit": round(category_profit, 3),
                    "order_count": stat.get("order_count", 0),
                    "on_shelf": bool(on_shelf),
                    "in_stock": bool(in_stock),
                    "available": bool(on_shelf) or not stock_known,
                    "cost_missing": False,
                })

        labels = {
            "stock_more": _("Stock more"),
            "review_price": _("Review price"),
            "kill": _("Did not sell"),
            "keep": _("Keep"),
            "not_stocked": _("Not in this branch"),
        }
        rows_by_branch = defaultdict(list)
        for row in rows:
            rows_by_branch[row["config_id"]].append(row)
        for branch_rows in rows_by_branch.values():
            sellers = [row for row in branch_rows if row["qty"] > 0]
            sales_with_margin = sum(row["sales"] for row in sellers if row["margin"] is not None and row["profit"] is not None)
            profit_with_margin = sum(
                row["sales"] - (row["cost"] or 0.0)
                for row in sellers
                if row["margin"] is not None and row["profit"] is not None
            )
            avg_margin = (profit_with_margin / sales_with_margin * 100.0) if sales_with_margin else 0.0
            ranked = sorted(sellers, key=lambda row: row["qty"], reverse=True)
            top_n = min(15, max(5, math.ceil(len(ranked) * 0.2))) if len(ranked) >= 5 else len(ranked)
            top_qty_ids = {row["product_id"] for row in ranked[:top_n]}
            for row in branch_rows:
                if row["qty"] <= 0 and not row["available"]:
                    decision = "not_stocked"
                elif row["qty"] <= 0:
                    decision = "kill"
                else:
                    decision = self._product_decision(row, top_qty_ids, avg_margin)
                row["decision"] = decision
                row["decision_label"] = labels[decision]

        sellers = [row for row in rows if row["qty"] > 0]
        sales_with_margin = sum(row["sales"] for row in sellers if row["margin"] is not None and row["profit"] is not None)
        profit_with_margin = sum(
            row["sales"] - (row["cost"] or 0.0)
            for row in sellers
            if row["margin"] is not None and row["profit"] is not None
        )
        avg_margin = (profit_with_margin / sales_with_margin * 100.0) if sales_with_margin else 0.0
        with_percentage = [row for row in rows if row["percentage"] is not None]
        category_profit_total = sum(row["category_profit"] for row in rows)
        category_buckets = {}
        product_buckets = {}
        for row in rows:
            bucket = category_buckets.setdefault(row["category"], {
                "name": row["category"],
                "category_profit": 0.0,
                "sales": 0.0,
            })
            bucket["category_profit"] += row["category_profit"]
            bucket["sales"] += row["sales"]
            product = product_buckets.setdefault(row["product_id"], {
                "product_id": row["product_id"],
                "name": row["name"],
                "category": row["category"],
                "category_profit": 0.0,
                "sales": 0.0,
                "on_shelf": False,
            })
            product["category_profit"] += row["category_profit"]
            product["sales"] += row["sales"]
            product["on_shelf"] = product["on_shelf"] or row["on_shelf"]
        for bucket in category_buckets.values():
            bucket["category_profit"] = round(bucket["category_profit"], 3)
            bucket["sales"] = round(bucket["sales"], 3)
        for product in product_buckets.values():
            product["category_profit"] = round(product["category_profit"], 3)
            product["sales"] = round(product["sales"], 3)
        best_categories = sorted(category_buckets.values(), key=lambda row: row["category_profit"], reverse=True)[:5]
        best_available = sorted(
            (row for row in product_buckets.values() if row["on_shelf"]),
            key=lambda row: row["category_profit"],
            reverse=True,
        )[:5]
        best_unavailable = sorted(
            (row for row in product_buckets.values() if not row["on_shelf"]),
            key=lambda row: row["category_profit"],
            reverse=True,
        )[:5]
        worst_in_stock = sorted(
            (row for row in rows if row["in_stock"]),
            key=lambda row: row["category_profit"],
        )[:5]
        category_cards = {
            "best_categories": best_categories,
            "best_available": best_available,
            "best_unavailable": best_unavailable,
            "worst_in_stock": worst_in_stock,
        }

        def _top(decision, key, reverse=True, limit=5):
            picked = [row for row in rows if row["decision"] == decision]
            picked.sort(key=lambda row: (row[key] is None, row[key] or 0), reverse=reverse)
            return picked[:limit]

        best_profit = sorted(
            (row for row in rows if row["profit"] is not None and row["qty"] > 0),
            key=lambda row: row["profit"],
        )[:5]
        kill_rows = sorted(
            (row for row in rows if row["decision"] == "kill"),
            key=lambda row: ((row["qty"] != 0), row["name"]),
        )

        categories = {}
        for row in rows:
            bucket = categories.setdefault(row["category"], {
                "name": row["category"],
                "qty": 0.0,
                "sales": 0.0,
                "profit": 0.0,
                "product_count": 0,
                "unsold_count": 0,
            })
            bucket["qty"] += row["qty"]
            bucket["sales"] += row["sales"]
            bucket["profit"] += row["profit"] or 0.0
            bucket["product_count"] += 1
            if row["decision"] == "kill":
                bucket["unsold_count"] += 1
        category_rows = sorted(categories.values(), key=lambda row: row["sales"], reverse=True)
        for bucket in category_rows:
            bucket["qty"] = round(bucket["qty"], 3)
            bucket["sales"] = round(bucket["sales"], 3)
            bucket["profit"] = round(bucket["profit"], 3)

        return {
            "date_from": fields.Date.to_string(period["date_from"]),
            "date_to": fields.Date.to_string(period["date_to"]),
            "summary": {
                "menu_count": len({row["product_id"] for row in rows}),
                "sold_count": len(sellers),
                "unsold_count": sum(row["decision"] == "kill" for row in rows),
                "not_stocked_count": sum(row["decision"] == "not_stocked" for row in rows),
                "total_qty": round(sum(row["qty"] for row in rows), 3),
                "total_sales": round(sum(row["sales"] for row in rows), 3),
                "total_profit": round(profit_with_margin, 3),
                "avg_margin": round(avg_margin, 1),
                "category_profit_total": round(category_profit_total, 3),
                "category_rated_count": len(with_percentage),
                "category_missing_count": len(rows) - len(with_percentage),
            },
            "cards": {
                "stock_more": _top("stock_more", "qty"),
                "best_profit": best_profit,
                "review_price": _top("review_price", "qty"),
                "kill": kill_rows[:8],
            },
            "categories": category_rows[:8],
            "category_cards": category_cards,
            "products": rows,
        }

    @api.model
    def _filter_product_export_rows(
        self,
        rows,
        product_filter="all",
        product_search="",
        sort_key="qty",
        sort_order="desc",
    ):
        """Match the Products view table: decision filter, search, and sort."""
        product_filter = product_filter or "all"
        query = (product_search or "").strip().lower()
        filtered = list(rows or [])
        if product_filter == "unsold":
            filtered = [row for row in filtered if row.get("decision") == "kill"]
        elif product_filter != "all":
            filtered = [row for row in filtered if row.get("decision") == product_filter]
        if query:
            filtered = [
                row
                for row in filtered
                if query in (row.get("name") or "").lower()
                or query in (row.get("branch_name") or "").lower()
                or query in (row.get("category") or "").lower()
            ]

        sort_key = sort_key or "qty"
        ascending = (sort_order or "desc") == "asc"
        text_keys = {"name", "branch_name", "category", "decision_label", "decision"}
        if sort_key in text_keys:
            filtered.sort(
                key=lambda row: (row.get(sort_key) or "").lower(),
                reverse=not ascending,
            )
        else:
            def _num_key(row):
                value = row.get(sort_key)
                if value is None:
                    return (1, 0)  # missing always last, same as the Products table
                return (0, value if ascending else -float(value))

            filtered.sort(key=_num_key)
        return filtered

    @api.model
    def _generate_products_xlsx(self, rows, date_from, date_to):
        import xlsxwriter

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet(_("POS menu"))

        title_fmt = workbook.add_format({"bold": True, "font_size": 14, "font_color": "#1A252C"})
        sub_fmt = workbook.add_format({"font_size": 10, "font_color": "#555555"})
        box_title_fmt = workbook.add_format({
            "bold": True,
            "font_size": 10,
            "bg_color": "#E8F0FE",
            "border": 1,
            "valign": "vcenter",
        })
        box_text_fmt = workbook.add_format({
            "font_size": 9,
            "bg_color": "#F8FBFF",
            "border": 1,
            "text_wrap": True,
            "valign": "top",
        })
        legend_label_fmt = workbook.add_format({
            "bold": True,
            "font_size": 9,
            "bg_color": "#FFF8E7",
            "border": 1,
            "valign": "vcenter",
        })
        legend_text_fmt = workbook.add_format({
            "font_size": 9,
            "bg_color": "#FFFDF6",
            "border": 1,
            "text_wrap": True,
            "valign": "top",
        })
        header_fmt = workbook.add_format({
            "bold": True,
            "bg_color": "#1F4E78",
            "font_color": "#FFFFFF",
            "border": 1,
            "align": "center",
            "valign": "vcenter",
        })
        text_fmt = workbook.add_format({"border": 1, "align": "left"})
        num_fmt = workbook.add_format({"border": 1, "num_format": "#,##0.000", "align": "right"})
        int_fmt = workbook.add_format({"border": 1, "num_format": "#,##0", "align": "right"})
        pct_fmt = workbook.add_format({"border": 1, "num_format": '0.0"%"', "align": "right"})
        empty_fmt = workbook.add_format({"border": 1, "align": "center", "font_color": "#888888"})

        # Title
        sheet.write(0, 0, _("POS menu"), title_fmt)

        # Box 1 — under title
        sheet.merge_range(1, 0, 1, 8, _("About this export"), box_title_fmt)
        sheet.merge_range(
            2,
            0,
            3,
            8,
            _(
                "One row per POS-menu product and branch for the selected period. "
                "Qty / Sales / Profit / Margin come from POS sales. "
                "The Decision column is a recommendation based on sold quantity and margin "
                "compared with other products in the same branch."
            ),
            box_text_fmt,
        )
        sheet.set_row(2, 18)
        sheet.set_row(3, 18)

        # Period / row count
        sheet.write(4, 0, _("Period: %s to %s") % (date_from, date_to), sub_fmt)
        sheet.write(5, 0, _("Rows: %s") % len(rows), sub_fmt)

        # Box 2 — decision legend under row count
        sheet.merge_range(6, 0, 6, 8, _("Decision meanings"), box_title_fmt)
        decision_lines = [
            (_("Stock more"), _(
                "Top sellers at this branch with margin at or above the branch average. Consider stocking more."
            )),
            (_("Review price"), _(
                "Top sellers with margin much below the branch average (under about 60% of average). Review pricing."
            )),
            (_("Keep"), _(
                "Sold in the period, but not flagged as Stock more or Review price."
            )),
            (_("Did not sell"), _(
                "Was on the shelf at this branch during the period and sold zero."
            )),
            (_("Not in this branch"), _(
                "Not available / not on the shelf at this branch during the period."
            )),
        ]
        legend_start = 7
        for offset, (label, meaning) in enumerate(decision_lines):
            row = legend_start + offset
            sheet.write(row, 0, label, legend_label_fmt)
            sheet.merge_range(row, 1, row, 8, meaning, legend_text_fmt)
            sheet.set_row(row, 28)

        header_row = legend_start + len(decision_lines) + 1
        headers = [
            _("Product"),
            _("Branch"),
            _("POS category"),
            _("Qty"),
            _("Sales"),
            _("Profit"),
            _("Margin"),
            _("Orders"),
            _("Decision"),
        ]
        for col, label in enumerate(headers):
            sheet.write(header_row, col, label, header_fmt)

        for row_idx, row in enumerate(rows, start=header_row + 1):
            sheet.write(row_idx, 0, row.get("name") or "", text_fmt)
            sheet.write(row_idx, 1, row.get("branch_name") or "", text_fmt)
            sheet.write(row_idx, 2, row.get("category") or "", text_fmt)
            sheet.write_number(row_idx, 3, float(row.get("qty") or 0.0), num_fmt)
            sheet.write_number(row_idx, 4, float(row.get("sales") or 0.0), num_fmt)
            if row.get("profit") is None:
                sheet.write(row_idx, 5, "—", empty_fmt)
            else:
                sheet.write_number(row_idx, 5, float(row["profit"]), num_fmt)
            if row.get("margin") is None:
                sheet.write(row_idx, 6, "—", empty_fmt)
            else:
                sheet.write_number(row_idx, 6, float(row["margin"]), pct_fmt)
            sheet.write_number(row_idx, 7, int(row.get("order_count") or 0), int_fmt)
            sheet.write(row_idx, 8, row.get("decision_label") or "", text_fmt)

        sheet.set_column(0, 0, 48)
        sheet.set_column(1, 1, 28)
        sheet.set_column(2, 2, 22)
        sheet.set_column(3, 7, 12)
        sheet.set_column(8, 8, 18)
        sheet.freeze_panes(header_row + 1, 0)
        workbook.close()
        return output.getvalue()

    @api.model
    def action_export_products_xlsx(
        self,
        date_from=None,
        date_to=None,
        config_ids=None,
        product_filter="all",
        product_search="",
        sort_key="qty",
        sort_order="desc",
    ):
        """Download the Products view table as Excel (current filters/search/sort)."""
        self._check_product_dashboard_access()
        data = self.get_product_dashboard_data(
            date_from=date_from,
            date_to=date_to,
            config_ids=config_ids,
        )
        rows = self._filter_product_export_rows(
            data.get("products") or [],
            product_filter=product_filter,
            product_search=product_search,
            sort_key=sort_key,
            sort_order=sort_order,
        )
        content = self._generate_products_xlsx(
            rows,
            data.get("date_from") or date_from or "",
            data.get("date_to") or date_to or "",
        )
        filename = "POS_Menu_%s_%s.xlsx" % (
            data.get("date_from") or date_from or "start",
            data.get("date_to") or date_to or "end",
        )
        attachment = self.env["ir.attachment"].sudo().create(
            {
                "name": filename,
                "type": "binary",
                "datas": base64.b64encode(content),
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "res_model": "pos.reporting.dashboard",
                "res_id": 0,
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    def _transfer_hub_locations(self):
        """Locations used as تسليم الطلبيات (order delivery) hubs."""
        Location = self.env["stock.location"].sudo()
        return Location.search([
            ("active", "=", True),
            ("usage", "=", "internal"),
            ("name", "ilike", "تسليم الطلبيات"),
        ])

    def _transfer_descendant_location_ids(self, roots):
        """Root stock locations plus every child under them."""
        if not roots:
            return set()
        Location = self.env["stock.location"].sudo()
        return set(Location.search([("id", "child_of", roots.ids)]).ids)

    def _transfer_is_return_picking(self, picking):
        origin = (picking.origin or "").strip().lower()
        if origin.startswith("return of") or origin.startswith("إرجاع") or origin.startswith("ارجاع"):
            return True
        if "return_id" in picking._fields and picking.return_id:
            return True
        return False

    def _transfer_move_qty(self, move, done_only=False):
        """Quantity in the move UoM. When done_only, zero unless the picking is Done."""
        if not move:
            return 0.0
        if done_only and move.picking_id and move.picking_id.state != "done":
            return 0.0
        return float(move.quantity or 0.0)

    def _transfer_move_uom(self, move):
        if not move:
            return False
        # Odoo 19 renamed stock.move.product_uom → uom_id (older DBs may still have product_uom).
        if "uom_id" in move._fields and move.uom_id:
            return move.uom_id
        if "product_uom" in move._fields and move.product_uom:
            return move.product_uom
        return False

    def _transfer_linked_moves_by_group_or_reference(
        self, move, picking, product, location_dest_ids, exclude_picking_id=None,
    ):
        """Sibling internal moves via procurement group (≤18) or reference_ids (19+).

        Odoo 19 removed ``stock.move.group_id`` (and often picking.group_id) in favour of
        ``reference_ids`` / ``stock.reference``.
        """
        Move = self.env["stock.move"].sudo()
        if not move or not product or not location_dest_ids:
            return Move.browse()
        domain_base = [
            ("product_id", "=", product.id),
            ("location_dest_id", "in", list(location_dest_ids)),
            ("state", "!=", "cancel"),
            ("picking_id", "!=", False),
        ]
        candidates = Move.browse()
        group = False
        if "group_id" in move._fields and move.group_id:
            group = move.group_id
        elif picking and "group_id" in picking._fields and picking.group_id:
            group = picking.group_id
        if group and "group_id" in Move._fields:
            candidates = Move.search(
                domain_base + [("group_id", "=", group.id)],
                order="id desc",
            )
        if not candidates and "reference_ids" in Move._fields:
            refs = False
            if "reference_ids" in move._fields and move.reference_ids:
                refs = move.reference_ids
            elif picking and "reference_ids" in picking._fields and picking.reference_ids:
                refs = picking.reference_ids
            if refs:
                candidates = Move.search(
                    domain_base + [("reference_ids", "in", refs.ids)],
                    order="id desc",
                )
        exclude_id = exclude_picking_id or 0
        return candidates.filtered(
            lambda m: m.picking_id
            and m.picking_id.id != exclude_id
            and m.picking_id.picking_type_code == "internal"
        )

    def _resolve_forward_receipt_move(self, send_move, branch_location_ids):
        """Next internal move after a تسليم الطلبيات → branch send (2-step routes).

        Many warehouses ship hub→branch as two pickings: the first
        (e.g. NAJ/INT/…) has empty ``move_orig_ids`` and pushes into a second
        branch picking (e.g. BASHA/INT/…) via ``move_dest_ids``. That first
        document is the send; the second is the real branch receipt.
        """
        Move = self.env["stock.move"].sudo()
        if not send_move or not send_move.product_id:
            return Move.browse()
        product = send_move.product_id
        send_picking = send_move.picking_id
        dest = send_move.move_dest_ids.filtered(
            lambda m: m.state != "cancel"
            and m.product_id == product
            and m.picking_id
            and m.picking_id.picking_type_code == "internal"
            and (not send_picking or m.picking_id.id != send_picking.id)
        )
        if branch_location_ids:
            dest_branch = dest.filtered(
                lambda m: m.location_dest_id.id in branch_location_ids
                or (m.picking_id and m.picking_id.location_dest_id.id in branch_location_ids)
            )
            if dest_branch:
                return dest_branch[:1]
        return dest[:1] if dest else Move.browse()

    def _resolve_request_move_for_receipt(self, receipt_move, hub_ids):
        """Find the hub request/send move that feeds this branch receipt move."""
        Move = self.env["stock.move"].sudo()
        Picking = self.env["stock.picking"].sudo()
        if not receipt_move or not receipt_move.product_id:
            return Move.browse()

        product = receipt_move.product_id
        receipt_picking = receipt_move.picking_id

        orig = receipt_move.move_orig_ids.filtered(
            lambda m: m.state != "cancel" and m.product_id == product
        )
        if orig:
            return orig[:1]

        incoming = Move.search(
            [
                ("move_dest_ids", "in", receipt_move.ids),
                ("product_id", "=", product.id),
                ("state", "!=", "cancel"),
            ],
            order="id desc",
            limit=1,
        )
        if incoming:
            return incoming

        hub_dest_ids = set(hub_ids or [])
        if receipt_picking and receipt_picking.location_id:
            hub_dest_ids.add(receipt_picking.location_id.id)

        if hub_dest_ids:
            candidates = self._transfer_linked_moves_by_group_or_reference(
                receipt_move,
                receipt_picking,
                product,
                hub_dest_ids,
                exclude_picking_id=receipt_picking.id if receipt_picking else 0,
            )
            linked = candidates.filtered(lambda m: receipt_move in m.move_dest_ids)
            if linked:
                return linked[:1]
            if candidates:
                return candidates[:1]

        origin = (receipt_picking.origin or "").strip() if receipt_picking else ""
        if origin and not origin.lower().startswith("return of"):
            req_picking = Picking.search(
                [
                    ("name", "=", origin),
                    ("state", "!=", "cancel"),
                    ("picking_type_code", "=", "internal"),
                ],
                limit=1,
            )
            if not req_picking and hub_dest_ids:
                req_picking = Picking.search(
                    [
                        ("name", "ilike", origin),
                        ("location_dest_id", "in", list(hub_dest_ids)),
                        ("state", "!=", "cancel"),
                        ("picking_type_code", "=", "internal"),
                    ],
                    limit=1,
                )
            if req_picking:
                req_move = req_picking.move_ids.filtered(
                    lambda m: m.state != "cancel" and m.product_id == product
                )[:1]
                if req_move:
                    return req_move

        return Move.browse()

    def _resolve_receipt_move_for_request(self, request_move, branch_location_ids):
        """Find the branch receipt move created from this hub request/send move."""
        Move = self.env["stock.move"].sudo()
        Picking = self.env["stock.picking"].sudo()
        if not request_move or not request_move.product_id:
            return Move.browse()

        product = request_move.product_id
        request_picking = request_move.picking_id

        dest = request_move.move_dest_ids.filtered(
            lambda m: m.state != "cancel" and m.product_id == product
        )
        if branch_location_ids:
            dest_branch = dest.filtered(
                lambda m: m.picking_id
                and m.picking_id.location_dest_id.id in branch_location_ids
            )
            if dest_branch:
                return dest_branch[:1]
        if dest:
            return dest[:1]

        if branch_location_ids:
            candidates = self._transfer_linked_moves_by_group_or_reference(
                request_move,
                request_picking,
                product,
                branch_location_ids,
                exclude_picking_id=request_picking.id if request_picking else 0,
            )
            linked = candidates.filtered(lambda m: request_move in m.move_orig_ids)
            if linked:
                return linked[:1]
            if candidates:
                return candidates[:1]

        if request_picking and branch_location_ids:
            receipt = Picking.search(
                [
                    ("origin", "=", request_picking.name),
                    ("location_dest_id", "in", list(branch_location_ids)),
                    ("state", "!=", "cancel"),
                    ("picking_type_code", "=", "internal"),
                ],
                order="id desc",
                limit=1,
            )
            if receipt:
                receipt_move = receipt.move_ids.filtered(
                    lambda m: m.state != "cancel" and m.product_id == product
                )[:1]
                if receipt_move:
                    return receipt_move

        return Move.browse()

    def _transfer_gap_where(self, asked, sent, received, receipt_state, has_receipt):
        """Where the mismatch happened for the supervisor."""
        send_gap = round(asked - sent, 3)
        receive_gap = round(sent - received, 3)
        not_approved = (not has_receipt) or (receipt_state not in ("done", "cancel"))
        parts = []
        if abs(send_gap) > 0.0005:
            parts.append("send")
        if not_approved:
            parts.append("waiting")
        elif abs(receive_gap) > 0.0005:
            parts.append("receive")
        if not parts:
            where = "ok"
            where_label = _("Match — asked, sent, and received agree")
        elif parts == ["send"]:
            where = "send"
            where_label = _("تسليم الطلبيات sent less than asked")
        elif parts == ["receive"]:
            where = "receive"
            where_label = _("Branch received less than sent")
        elif parts == ["waiting"]:
            where = "waiting"
            where_label = _("Branch receipt not validated yet")
        elif "send" in parts and "waiting" in parts:
            where = "send_waiting"
            where_label = _("تسليم الطلبيات short + receipt not validated")
        elif "send" in parts and "receive" in parts:
            where = "both"
            where_label = _("Short at تسليم الطلبيات and again at branch")
        else:
            where = "mixed"
            where_label = _("Mixed issue")
        return {
            "send_gap": send_gap,
            "receive_gap": receive_gap if not not_approved else round(sent - received, 3),
            "not_approved": not_approved,
            "where": where,
            "where_label": where_label,
        }

    def _transfer_state_label(self, state):
        labels = {
            "draft": _("Draft"),
            "waiting": _("Waiting"),
            "confirmed": _("Waiting"),
            "assigned": _("Ready"),
            "done": _("Done"),
            "cancel": _("Cancelled"),
        }
        return labels.get(state, state or "")

    def _check_transfer_dashboard_access(self):
        if not self.env.user.has_group("anabtawi_pos_reporting_dashboard.group_pos_dashboard_transfers"):
            raise AccessError(_("You are not allowed to view the Transfers section of the POS dashboard."))

    def _transfer_prefetch_pairing_graph(self, pickings):
        """Warm ORM cache for moves and 1-hop chain links (avoids N+1 in pairing)."""
        if not pickings:
            return self.env["stock.move"].browse()
        moves = pickings.mapped("move_ids")
        related = moves.mapped("move_dest_ids") | moves.mapped("move_orig_ids")
        related_pickings = related.mapped("picking_id")
        warm = pickings | related_pickings
        warm.mapped("move_ids")
        warm.mapped("move_ids.product_id")
        warm.mapped("move_ids.move_dest_ids")
        warm.mapped("move_ids.move_orig_ids")
        warm.mapped("location_id")
        warm.mapped("location_dest_id")
        warm.mapped("picking_type_id")
        warm.mapped("origin")
        return moves | related

    def _transfer_filter_sort_paginate_rows(
        self, rows, row_filter="all", row_search="", sort_key="where", sort_order="asc",
        page=1, page_size=50,
    ):
        """Apply Transfers table filter/search/sort then slice one page."""
        row_filter = (row_filter or "all").strip()
        query = (row_search or "").strip().lower()
        filtered = rows
        if row_filter == "mismatch":
            filtered = [r for r in filtered if r.get("where") != "ok"]
        elif row_filter == "not_approved":
            filtered = [r for r in filtered if r.get("not_approved")]
        elif row_filter == "send":
            filtered = [r for r in filtered if abs(float(r.get("send_gap") or 0.0)) > 0.0005]
        elif row_filter == "receive":
            filtered = [
                r for r in filtered
                if not r.get("not_approved") and abs(float(r.get("receive_gap") or 0.0)) > 0.0005
            ]
        if query:
            def _match(r):
                blob = " ".join([
                    r.get("product_name") or "",
                    r.get("branch_name") or "",
                    r.get("request_picking_name") or "",
                    r.get("receipt_picking_name") or "",
                    r.get("where_label") or "",
                ]).lower()
                return query in blob
            filtered = [r for r in filtered if _match(r)]

        where_rank = {
            "waiting": 0,
            "send_waiting": 1,
            "both": 2,
            "send": 3,
            "receive": 4,
            "mixed": 5,
            "ok": 6,
        }
        key = sort_key or "where"
        reverse = (sort_order or "asc") == "desc"

        def _sort_key_fn(r):
            if key == "where":
                return (0, where_rank.get(r.get("where"), 9), "")
            val = r.get(key)
            if isinstance(val, str):
                return (1, 0, (val or "").lower())
            if val is None:
                return (2, 0, "")
            try:
                return (0, float(val), "")
            except (TypeError, ValueError):
                return (1, 0, str(val).lower())

        filtered.sort(key=_sort_key_fn, reverse=reverse)

        page_size = max(10, min(int(page_size or 50), 200))
        page = max(1, int(page or 1))
        total = len(filtered)
        total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
        if page > total_pages:
            page = total_pages
        start = (page - 1) * page_size
        page_rows = filtered[start:start + page_size]
        return page_rows, {
            "page": page,
            "page_size": page_size,
            "total_rows": total,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
        }

    @api.model
    def get_transfer_dashboard_data(
        self,
        date_from=None,
        date_to=None,
        config_ids=None,
        page=1,
        page_size=50,
        row_filter="all",
        row_search="",
        sort_key="where",
        sort_order="asc",
    ):
        """Branch request → تسليم الطلبيات send → branch receive, per product line."""
        self._check_transfer_dashboard_access()
        period = self._parse_period(date_from, date_to)
        _dt_start, _dt_end, start_str, end_str = self._period_bounds(period)
        configs = self._get_report_configs(config_ids)
        all_configs = self._get_report_configs()
        Picking = self.env["stock.picking"].sudo()
        hub_locations = self._transfer_hub_locations()
        hub_ids = set(hub_locations.ids)

        empty = {
            "date_from": period["date_from"].isoformat(),
            "date_to": period["date_to"].isoformat(),
            "all_branches": [{"id": c.id, "name": c.name} for c in all_configs],
            "summary": {
                "line_count": 0,
                "asked": 0.0,
                "sent": 0.0,
                "received": 0.0,
                "send_gap": 0.0,
                "receive_gap": 0.0,
                "not_approved_count": 0,
                "mismatch_count": 0,
            },
            "rows": [],
            "error": "",
        }
        if not hub_ids:
            empty["error"] = _("No تسليم الطلبيات location was found.")
            return empty
        if not configs:
            return empty

        config_by_location = {}
        branch_location_ids = set()
        config_location_ids = {}
        TransferMap = self.env["pos.dashboard.transfer.location"].sudo()
        mapped_configs = TransferMap.search([
            ("config_id", "in", configs.ids),
            ("active", "=", True),
        ]).mapped("config_id")
        for config in configs:
            root = self._config_transfer_stock_location(config)
            if not root:
                continue
            loc_ids = self._transfer_descendant_location_ids(root)
            config_location_ids[config.id] = loc_ids
            for loc_id in loc_ids:
                branch_location_ids.add(loc_id)
                config_by_location.setdefault(loc_id, config)

        if not branch_location_ids:
            empty["error"] = _(
                "No transfer stock location is linked to the selected POS branches. "
                "Open Point of Sale → Reporting → POS Transfer Locations and assign each branch."
            )
            return empty

        date_domain = [
            "|", "|",
            "&", ("scheduled_date", ">=", start_str), ("scheduled_date", "<", end_str),
            "&", ("date_done", ">=", start_str), ("date_done", "<", end_str),
            "&", ("create_date", ">=", start_str), ("create_date", "<", end_str),
        ]
        base_domain = [
            ("picking_type_code", "=", "internal"),
            ("state", "!=", "cancel"),
        ] + date_domain

        receipt_pickings = Picking.search(
            base_domain
            + [
                ("location_id", "in", list(hub_ids)),
                ("location_dest_id", "in", list(branch_location_ids)),
            ],
            order="scheduled_date desc, id desc",
        )
        # Only asks that leave a mapped branch location (skips unrelated hub traffic).
        request_pickings = Picking.search(
            base_domain
            + [
                ("location_dest_id", "in", list(hub_ids)),
                ("location_id", "in", list(branch_location_ids)),
            ],
            order="scheduled_date desc, id desc",
        )

        self._transfer_prefetch_pairing_graph(request_pickings | receipt_pickings)

        # One shot for origin-name pairing instead of per-move searches.
        origin_names = {
            (p.origin or "").strip()
            for p in receipt_pickings
            if (p.origin or "").strip() and not (p.origin or "").strip().lower().startswith("return of")
        }
        origin_pickings = Picking.browse()
        if origin_names:
            origin_pickings = Picking.search([
                ("name", "in", list(origin_names)),
                ("state", "!=", "cancel"),
                ("picking_type_code", "=", "internal"),
            ])
            self._transfer_prefetch_pairing_graph(origin_pickings)
        picking_by_name = {p.name: p for p in (request_pickings | origin_pickings) if p.name}

        # Reverse chain index: receipt_move.id → request/send move (from prefetched dest links).
        dest_move_to_request = {}
        for req_picking in request_pickings:
            for req_move in req_picking.move_ids:
                if req_move.state == "cancel" or not req_move.product_id:
                    continue
                for dest_move in req_move.move_dest_ids:
                    if dest_move.state != "cancel":
                        dest_move_to_request.setdefault(dest_move.id, req_move)

        def _config_for_pair(request_picking=False, receipt_picking=False):
            if receipt_picking:
                config = config_by_location.get(receipt_picking.location_dest_id.id)
                if config:
                    return config
            if request_picking:
                config = config_by_location.get(request_picking.location_id.id)
                if config:
                    return config
                op_name = request_picking.picking_type_id.name or ""
                for candidate in configs:
                    if candidate.name and candidate.name in op_name:
                        return candidate
                    loc_ids = config_location_ids.get(candidate.id) or set()
                    if request_picking.location_id.id in loc_ids:
                        return candidate
            return False

        def _request_move_fast(receipt_move):
            """In-memory request lookup; avoids per-line Move/Picking.search."""
            Move = self.env["stock.move"].sudo()
            if not receipt_move or not receipt_move.product_id:
                return Move.browse()
            product = receipt_move.product_id
            cached = dest_move_to_request.get(receipt_move.id)
            if cached and cached.product_id == product:
                return cached
            orig = receipt_move.move_orig_ids.filtered(
                lambda m: m.state != "cancel" and m.product_id == product
            )
            if orig:
                return orig[:1]
            receipt_picking = receipt_move.picking_id
            origin = (receipt_picking.origin or "").strip() if receipt_picking else ""
            if origin and not origin.lower().startswith("return of"):
                req_picking = picking_by_name.get(origin)
                if req_picking:
                    req_move = req_picking.move_ids.filtered(
                        lambda m: m.state != "cancel" and m.product_id == product
                    )[:1]
                    if req_move:
                        return req_move
            # Rare fallback (reference_ids / odd chains).
            return self._resolve_request_move_for_receipt(receipt_move, hub_ids)

        rows = []
        seen = set()
        paired_receipt_move_ids = set()
        paired_request_move_ids = set()

        def _append_row(config, product, uom, asked, sent, received, request_picking, receipt_picking):
            key = (
                config.id if config else 0,
                product.id,
                request_picking.id if request_picking else 0,
                receipt_picking.id if receipt_picking else 0,
            )
            if key in seen:
                return
            seen.add(key)
            receipt_state = receipt_picking.state if receipt_picking else False
            has_receipt = bool(receipt_picking)
            gap = self._transfer_gap_where(
                asked, sent, received, receipt_state or "", has_receipt
            )
            rows.append({
                "row_key": "%s-%s-%s-%s" % key,
                "config_id": config.id if config else False,
                "branch_name": config.name if config else "",
                "product_id": product.id,
                "product_name": product.display_name,
                "uom": uom.display_name if uom else "",
                "asked": round(asked, 3),
                "sent": round(sent, 3),
                "received": round(received, 3),
                "send_gap": gap["send_gap"],
                "receive_gap": gap["receive_gap"],
                "not_approved": gap["not_approved"],
                "where": gap["where"],
                "where_label": gap["where_label"],
                "request_picking_id": request_picking.id if request_picking else False,
                "request_picking_name": request_picking.name if request_picking else "",
                "request_state": request_picking.state if request_picking else "",
                "request_state_label": self._transfer_state_label(request_picking.state) if request_picking else "",
                "receipt_picking_id": receipt_picking.id if receipt_picking else False,
                "receipt_picking_name": receipt_picking.name if receipt_picking else "",
                "receipt_state": receipt_state or "",
                "receipt_state_label": (
                    self._transfer_state_label(receipt_state) if receipt_state
                    else _("Not created")
                ),
            })

        def _quantities_from_pair(request_move, receipt_move):
            """Asked = demand; Sent = hub done qty; Received = branch done qty.

            When only a hub→branch receipt exists (no paired request), use that
            move's demand as Asked and its done quantity as both Sent and the
            starting point for Received — never treat demand as Sent, or a
            partial ship is mis-labeled as a receive gap.
            """
            asked = float((request_move.product_uom_qty if request_move else (
                receipt_move.product_uom_qty if receipt_move else 0.0
            )) or 0.0)
            if request_move:
                sent = self._transfer_move_qty(request_move, done_only=True)
            elif receipt_move:
                sent = self._transfer_move_qty(receipt_move, done_only=True)
            else:
                sent = 0.0
            received = self._transfer_move_qty(receipt_move, done_only=True) if receipt_move else 0.0
            return asked, sent, received

        # Pass 1: requests that already have a branch receipt (Asked/Sent from request).
        for picking in request_pickings:
            if self._transfer_is_return_picking(picking):
                continue
            for move in picking.move_ids.filtered(lambda m: m.state != "cancel" and m.product_id):
                if move.id in paired_request_move_ids:
                    continue
                receipt_move = self._resolve_receipt_move_for_request(move, branch_location_ids)
                if not receipt_move:
                    continue
                receipt_picking = receipt_move.picking_id
                if receipt_picking and self._transfer_is_return_picking(receipt_picking):
                    continue
                config = _config_for_pair(picking, receipt_picking)
                if not config:
                    continue
                asked, sent, received = _quantities_from_pair(move, receipt_move)
                _append_row(
                    config,
                    move.product_id,
                    self._transfer_move_uom(move),
                    asked,
                    sent,
                    received,
                    picking,
                    receipt_picking,
                )
                paired_request_move_ids.add(move.id)
                paired_receipt_move_ids.add(receipt_move.id)

        # Pass 2: hub→branch pickings in period (may be 2-step: send then branch receipt).
        for picking in receipt_pickings:
            if self._transfer_is_return_picking(picking):
                continue
            config = config_by_location.get(picking.location_dest_id.id)
            if not config:
                continue
            for move in picking.move_ids.filtered(lambda m: m.state != "cancel" and m.product_id):
                if move.id in paired_request_move_ids or move.id in paired_receipt_move_ids:
                    continue

                # 2-step: this hub→branch move feeds a later branch picking → treat
                # current as تسليم الطلبيات send/request, next as branch receipt.
                next_receipt = self._resolve_forward_receipt_move(move, branch_location_ids)
                if next_receipt:
                    if next_receipt.id in paired_receipt_move_ids:
                        continue
                    next_picking = next_receipt.picking_id
                    if next_picking and self._transfer_is_return_picking(next_picking):
                        next_receipt = self.env["stock.move"].browse()
                        next_picking = False
                    if next_receipt:
                        asked, sent, received = _quantities_from_pair(move, next_receipt)
                        _append_row(
                            config,
                            move.product_id,
                            self._transfer_move_uom(move),
                            asked,
                            sent,
                            received,
                            picking,
                            next_picking,
                        )
                        paired_request_move_ids.add(move.id)
                        paired_receipt_move_ids.add(next_receipt.id)
                        continue

                request_move = _request_move_fast(move)
                request_picking = request_move.picking_id if request_move else False
                if request_picking and self._transfer_is_return_picking(request_picking):
                    request_move = self.env["stock.move"].browse()
                    request_picking = False
                if request_move and request_move.id in paired_request_move_ids:
                    continue
                asked, sent, received = _quantities_from_pair(request_move, move)
                _append_row(
                    config,
                    move.product_id,
                    self._transfer_move_uom(request_move or move),
                    asked,
                    sent,
                    received,
                    request_picking,
                    picking,
                )
                paired_receipt_move_ids.add(move.id)
                if request_move:
                    paired_request_move_ids.add(request_move.id)

        # Pass 3: requests still without a receipt (not approved / not created).
        for picking in request_pickings:
            if self._transfer_is_return_picking(picking):
                continue
            for move in picking.move_ids.filtered(lambda m: m.state != "cancel" and m.product_id):
                if move.id in paired_request_move_ids:
                    continue
                config = _config_for_pair(picking, False)
                if not config:
                    continue
                asked, sent, received = _quantities_from_pair(move, False)
                _append_row(
                    config,
                    move.product_id,
                    self._transfer_move_uom(move),
                    asked,
                    sent,
                    received,
                    picking,
                    False,
                )
                paired_request_move_ids.add(move.id)

        rows.sort(key=lambda r: (
            0 if r["not_approved"] else 1,
            0 if r["where"] != "ok" else 1,
            r["branch_name"] or "",
            r["product_name"] or "",
        ))

        summary = {
            "line_count": len(rows),
            "asked": round(sum(r["asked"] for r in rows), 3),
            "sent": round(sum(r["sent"] for r in rows), 3),
            "received": round(sum(r["received"] for r in rows), 3),
            "send_gap": round(sum(r["send_gap"] for r in rows), 3),
            "receive_gap": round(sum(r["receive_gap"] for r in rows if not r["not_approved"]), 3),
            "not_approved_count": sum(1 for r in rows if r["not_approved"]),
            "mismatch_count": sum(1 for r in rows if r["where"] != "ok"),
        }
        page_rows, pagination = self._transfer_filter_sort_paginate_rows(
            rows,
            row_filter=row_filter,
            row_search=row_search,
            sort_key=sort_key,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )
        warning = ""
        if not mapped_configs:
            warning = _(
                "No POS Transfer Locations are configured yet. "
                "Assign each branch under Point of Sale → Reporting → POS Transfer Locations "
                "so receipts match the correct stock location."
            )
        elif len(mapped_configs) < len(configs):
            missing = configs - mapped_configs
            warning = _(
                "Some branches have no transfer location assigned: %s"
            ) % ", ".join(missing.mapped("name"))

        return {
            "date_from": period["date_from"].isoformat(),
            "date_to": period["date_to"].isoformat(),
            "all_branches": [{"id": c.id, "name": c.name} for c in all_configs],
            "summary": summary,
            "rows": page_rows,
            "pagination": pagination,
            "error": warning,
        }

    @api.model
    def open_transfer_picking(self, picking_id):
        """Open one internal transfer from the Transfers dashboard."""
        self._check_transfer_dashboard_access()
        picking = self.env["stock.picking"].browse(int(picking_id or 0)).exists()
        if not picking:
            raise AccessError(_("Transfer not found."))
        action = {
            "name": picking.name,
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": picking.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
            "context": {"create": False},
        }
        return action

    @api.model
    def open_product_lines(self, product_id, date_from=None, date_to=None, config_ids=None, config_id=None):
        """Open the POS order lines of one menu product in this search."""
        self._check_product_dashboard_access()
        engine = self.env["pos.daily.ops.engine"]
        period = self._parse_period(date_from, date_to)
        configs = self._get_report_configs(config_ids)
        if config_id:
            configs = self.env["pos.config"].browse(config_id).exists()
        sessions = engine._get_sessions(period, configs)
        product = self.env["product.product"].browse(product_id).exists()
        list_view = self.env.ref("point_of_sale.view_pos_order_line")
        form_view = self.env.ref("point_of_sale.view_pos_order_line_form")
        return {
            "name": product.display_name if product else _("Product sales"),
            "type": "ir.actions.act_window",
            "res_model": "pos.order.line",
            "view_mode": "list,form",
            "views": [(list_view.id, "list"), (form_view.id, "form")],
            "domain": [
                ("product_id", "=", product_id),
                ("order_id.session_id", "in", sessions.ids or [0]),
                ("order_id.state", "in", ("paid", "done", "invoiced")),
                ("is_gift", "=", False),
            ],
            "target": "current",
            "context": {"create": False, "delete": False},
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

        # Sessions the search included: opened on a selected branch inside the period.
        if metric_type == "sessions":
            return self._open_session_drilldown(period, configs)

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
        non_product_order_ids = engine._get_non_product_sales_order_ids(sessions)
        # Total POS Income keeps pledge/advance money; product sales KPIs do not.
        product_only_metrics = (
            "cash_sales", "visa_sales", "employee_debt", "online_sales",
            "untaxed_sales", "tax_amount", "avg_basket",
        )

        if metric_type in PAYMENT_METRICS:
            for pay in engine._get_payments(sessions):
                pm = pay.payment_method_id
                if not self._payment_matches_metric(pm, metric_type):
                    continue
                po = pay.pos_order_id
                if metric_type in product_only_metrics and po and po.id in non_product_order_ids:
                    continue
                bucket = engine._get_bucket(pm)
                cfg = pay.session_id.config_id
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
                po = pay.pos_order_id
                if po and po.id in non_product_order_ids:
                    continue
                untaxed_amt, tax_amt = self._payment_tax_split(pay)
                if (untaxed_amt if metric_type == "untaxed_sales" else tax_amt) == 0.0:
                    continue
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
            for order, income in self._get_paying_orders(sessions, non_product_order_ids).items():
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

    def _open_period_expense_drilldown(self, period):
        expenses = self._get_period_pos_expenses(period)
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
                expense_pending_amount += amt
                expense_pending_count += 1

        expense_amount = expense_approved_amount + expense_pending_amount
        expense_count = expense_approved_count + expense_pending_count

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

