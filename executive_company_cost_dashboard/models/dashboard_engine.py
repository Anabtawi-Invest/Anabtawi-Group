# -*- coding: utf-8 -*-
"""Data engine of the Executive Company Cost Dashboard.

Design rules
------------
* Strictly read-only: only SELECT statements, nothing is written to accounting tables.
* Reconciles with Odoo's own Profit & Loss: the P&L sections come from the account type
  (Income / Cost of Revenue / Expenses / Depreciation / Other Income) and only posted
  journal items are counted. Buckets are a second, functional view of the very same
  numbers (rent, payroll, utilities...), so they always add up to the P&L.
* Fast: three small GROUP BY queries (period, previous period, 12-month trend) plus one
  for the analytic distribution. Everything else is derived in memory.
* Multi-company safe: raw SQL is restricted to the companies the user may access.
"""
import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta

import pytz
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from .classifier import (
    INCOME_TYPES,
    PL_TYPES,
    SECTION_OF_TYPE,
    classify_account,
    classify_analytic,
    load_rules,
    normalize,
    platform_of,
)

GROUP_VIEWER = "executive_company_cost_dashboard.group_ceo_cost_dashboard_viewer"
GROUP_MANAGER = "executive_company_cost_dashboard.group_ceo_cost_dashboard_manager"

PERIOD_SHIFT = {
    "this_month": relativedelta(months=1),
    "last_month": relativedelta(months=1),
    "qtd": relativedelta(months=3),
    "ytd": relativedelta(years=1),
    "year": relativedelta(years=1),
    "last_12m": relativedelta(years=1),
}
DEFAULTS = {
    "ecd.branch_healthy_margin": 10.0,  # % net margin: at/above = healthy
    "ecd.rent_warn_pct": 15.0,  # rent / revenue %
    "ecd.rent_danger_pct": 20.0,
    "ecd.delivery_warn_pct": 8.0,  # delivery platform cost / revenue %
    "ecd.loss_warn_pct": 1.0,  # waste & shrinkage / revenue %
    "ecd.cost_jump_pct": 20.0,  # bucket growth vs previous period that raises an alert
}
SEVERITY = {"danger": 0, "warning": 1, "info": 2, "success": 3}


def _pct(part, whole):
    return round(part / whole * 100.0, 2) if whole else 0.0


def _delta(cur, prev):
    if not prev:
        return None
    return round((cur - prev) / abs(prev) * 100.0, 2)


class CeoCostDashboardReport(models.AbstractModel):
    _name = "ceo.cost.dashboard.report"
    _description = "Executive Company Cost Dashboard Engine"

    # ------------------------------------------------------------------
    # Public API (called by the OWL client action)
    # ------------------------------------------------------------------
    @api.model
    def run_smart_scan_direct(self):
        self._check_access(manager=True)
        return self.env["ceo.smart.scanner.wizard"].sudo()._scan(overwrite=True)

    @api.model
    def get_executive_dashboard_data(self, filters=None):
        self._check_access()
        filters = filters or {}
        self.env.flush_all()

        today = fields.Date.context_today(self)
        period = self._resolve_period(filters, today)
        companies = self._allowed_companies()
        selected = int(filters.get("company_id") or 0)
        if selected not in companies.ids:
            selected = 0
        sel_ids = [selected] if selected else companies.ids
        all_ids = companies.ids
        currency = self._currency(companies, selected)
        decimals = currency.decimal_places

        cube_cur = self._fetch_cube(all_ids, period["date_from"], period["date_to"])
        cube_prev = self._fetch_cube(all_ids, period["prev_from"], period["prev_to"])
        trend_from = period["date_to"].replace(day=1) - relativedelta(months=11)
        trend_to = period["date_to"].replace(day=1) + relativedelta(months=1) - relativedelta(days=1)
        cube_trend = self._fetch_trend(all_ids, trend_from, trend_to)

        resolver = self._bucket_resolver(
            {r[0] for r in cube_cur} | {r[0] for r in cube_prev} | {r[0] for r in cube_trend}
        )
        buckets = resolver["buckets"]
        bucket_of = resolver["bucket_of"]

        sel_set = set(sel_ids)
        cur = self._aggregate(cube_cur, bucket_of, sel_set)
        prev = self._aggregate(cube_prev, bucket_of, sel_set)
        summary = self._summary(cur["section"])
        prev_summary = self._summary(prev["section"])

        monthly = self._monthly(cube_trend, bucket_of, sel_set, trend_from, trend_to)
        bucket_rows = self._bucket_rows(
            buckets, cur, prev, monthly["by_bucket"], monthly["months"], summary, resolver, decimals
        )
        platforms = self._platforms(cur["account"], resolver, summary["revenue"])
        companies_rows = self._companies(companies, cube_cur, cube_prev, bucket_of, resolver, decimals)

        branches, departments = self._analytic_views(
            sel_ids, period, bucket_of, resolver, summary, cur["section"], decimals
        )

        thresholds = {k.split(".", 1)[1]: self._param(k) for k in DEFAULTS}
        alerts = self._alerts(summary, prev_summary, bucket_rows, branches, departments, companies_rows, thresholds,
                              resolver, currency, companies)

        return {
            "meta": {
                "generated_at": fields.Datetime.to_string(fields.Datetime.now()),
                "is_manager": self.env.user.has_group(GROUP_MANAGER) or self.env.user.has_group("base.group_system"),
                "purchasing_action_id": self._purchasing_action_id(),
                "lines": sum(r[5] for r in cube_cur if r[2] in sel_set),
                "unmapped_accounts": resolver["unmapped"],
                "multi_currency": len({c.currency_id.id for c in companies}) > 1,
            },
            "currency": {
                "name": currency.name or "",
                "symbol": currency.symbol or "",
                "position": currency.position or "after",
                "decimals": decimals,
            },
            "period": {
                "mode": period["mode"],
                "year": period["year"],
                "date_from": fields.Date.to_string(period["date_from"]),
                "date_to": fields.Date.to_string(period["date_to"]),
                "prev_from": fields.Date.to_string(period["prev_from"]),
                "prev_to": fields.Date.to_string(period["prev_to"]),
                "years": self._available_years(all_ids),
            },
            "filters": {"company_id": selected, "company_ids": sel_ids},
            "companies_available": [{"id": c.id, "name": c.name} for c in companies],
            "summary": self._round_dict(summary, decimals),
            "prev_summary": self._round_dict(prev_summary, decimals),
            "buckets": bucket_rows,
            "monthly": monthly["rows"],
            "companies": companies_rows,
            "branches": branches,
            "departments": departments,
            "platforms": platforms,
            "alerts": alerts,
            "thresholds": thresholds,
        }

    # ------------------------------------------------------------------
    # Access, parameters, companies
    # ------------------------------------------------------------------
    def _check_access(self, manager=False):
        user = self.env.user
        if user.has_group("base.group_system"):
            return
        if not user.has_group(GROUP_MANAGER if manager else GROUP_VIEWER):
            raise AccessError(_("You are not allowed to access the Executive Company Cost Dashboard."))

    def _param(self, key):
        raw = self.env["ir.config_parameter"].sudo().get_param(key)
        try:
            return float(raw) if raw not in (None, False, "") else DEFAULTS[key]
        except (TypeError, ValueError):
            return DEFAULTS[key]

    def _allowed_companies(self):
        return self.env.user.sudo().company_ids.sorted("sequence")

    def _currency(self, companies, selected):
        if selected:
            return self.env["res.company"].browse(selected).currency_id
        main = companies.filtered(lambda c: not c.parent_id)[:1] or companies[:1] or self.env.company
        return main.currency_id

    def _purchasing_action_id(self):
        """Soft link to the CEO Main Dashboard (purchasing) when it is installed."""
        group = self.env.ref("ceo_main_dashboard.group_ceo_main_dashboard_user", raise_if_not_found=False)
        action = self.env.ref("ceo_main_dashboard.action_ceo_main_dashboard", raise_if_not_found=False)
        if not group or not action or not self.env.user.has_group("ceo_main_dashboard.group_ceo_main_dashboard_user"):
            return False
        return action.id

    # ------------------------------------------------------------------
    # Period handling
    # ------------------------------------------------------------------
    def _resolve_period(self, filters, today):
        mode = filters.get("period_mode") or "ytd"
        year = int(filters.get("year") or today.year)
        if mode == "this_month":
            date_from = today.replace(day=1)
            date_to = today
        elif mode == "last_month":
            date_to = today.replace(day=1) - timedelta(days=1)
            date_from = date_to.replace(day=1)
        elif mode == "qtd":
            date_from = today.replace(month=((today.month - 1) // 3) * 3 + 1, day=1)
            date_to = today
        elif mode == "last_12m":
            date_to = today
            date_from = (today - relativedelta(months=11)).replace(day=1)
        elif mode == "year":
            date_from, date_to = date(year, 1, 1), date(year, 12, 31)
        elif mode == "custom":
            date_from = fields.Date.to_date(filters.get("date_from")) or today.replace(day=1)
            date_to = fields.Date.to_date(filters.get("date_to")) or today
            if date_from > date_to:
                date_from, date_to = date_to, date_from
        else:  # ytd
            mode = "ytd"
            date_from, date_to = today.replace(month=1, day=1), today

        shift = PERIOD_SHIFT.get(mode)
        if shift:
            prev_from, prev_to = date_from - shift, date_to - shift
            if mode == "last_month":  # a full month is compared with the full month before it
                prev_to = date_from - timedelta(days=1)
        else:
            span = (date_to - date_from).days + 1
            prev_to = date_from - timedelta(days=1)
            prev_from = prev_to - timedelta(days=span - 1)
        return {
            "mode": mode,
            "year": date_to.year if mode != "year" else year,
            "date_from": date_from,
            "date_to": date_to,
            "prev_from": prev_from,
            "prev_to": prev_to,
        }

    def _available_years(self, company_ids):
        if not company_ids:
            return []
        self.env.cr.execute(
            "SELECT MIN(date), MAX(date) FROM account_move_line WHERE parent_state = 'posted' AND company_id IN %s",
            (tuple(company_ids),),
        )
        low, high = self.env.cr.fetchone()
        if not low:
            return [fields.Date.context_today(self).year]
        return list(range(high.year, low.year - 1, -1))

    # ------------------------------------------------------------------
    # SQL (read-only)
    # ------------------------------------------------------------------
    def _fetch_cube(self, company_ids, date_from, date_to):
        """Rows (account_id, account_type, company_id, debit, credit, lines)."""
        if not company_ids:
            return []
        self.env.cr.execute(
            """
            SELECT aml.account_id, acc.account_type, aml.company_id,
                   COALESCE(SUM(aml.debit), 0), COALESCE(SUM(aml.credit), 0), COUNT(*)
              FROM account_move_line aml
              JOIN account_account acc ON acc.id = aml.account_id
             WHERE aml.parent_state = 'posted'
               AND aml.company_id IN %s
               AND aml.date BETWEEN %s AND %s
               AND acc.account_type IN %s
             GROUP BY aml.account_id, acc.account_type, aml.company_id
            """,
            (tuple(company_ids), date_from, date_to, PL_TYPES),
        )
        return [(r[0], r[1], r[2], float(r[3]), float(r[4]), r[5]) for r in self.env.cr.fetchall()]

    def _fetch_trend(self, company_ids, date_from, date_to):
        """Rows (account_id, account_type, company_id, debit, credit, month 'YYYY-MM')."""
        if not company_ids:
            return []
        self.env.cr.execute(
            """
            SELECT aml.account_id, acc.account_type, aml.company_id,
                   COALESCE(SUM(aml.debit), 0), COALESCE(SUM(aml.credit), 0),
                   TO_CHAR(aml.date, 'YYYY-MM')
              FROM account_move_line aml
              JOIN account_account acc ON acc.id = aml.account_id
             WHERE aml.parent_state = 'posted'
               AND aml.company_id IN %s
               AND aml.date BETWEEN %s AND %s
               AND acc.account_type IN %s
             GROUP BY aml.account_id, acc.account_type, aml.company_id, TO_CHAR(aml.date, 'YYYY-MM')
            """,
            (tuple(company_ids), date_from, date_to, PL_TYPES),
        )
        return [(r[0], r[1], r[2], float(r[3]), float(r[4]), r[5]) for r in self.env.cr.fetchall()]

    def _fetch_analytic_cube(self, company_ids, date_from, date_to):
        """Rows (analytic_id, account_id, account_type, net) where net = credit - debit
        distributed with the analytic percentages of each posted journal item."""
        if not company_ids:
            return []
        self.env.cr.execute(
            """
            SELECT aid.id::int AS analytic_id, aml.account_id, acc.account_type,
                   SUM((aml.credit - aml.debit) * d.pct::numeric / 100.0) AS net
              FROM account_move_line aml
              JOIN account_account acc ON acc.id = aml.account_id
             CROSS JOIN LATERAL jsonb_each_text(aml.analytic_distribution) AS d(k, pct)
             CROSS JOIN LATERAL regexp_split_to_table(d.k, ',') AS aid(id)
             WHERE aml.parent_state = 'posted'
               AND aml.analytic_distribution IS NOT NULL
               AND aml.company_id IN %s
               AND aml.date BETWEEN %s AND %s
               AND acc.account_type IN %s
             GROUP BY aid.id::int, aml.account_id, acc.account_type
            """,
            (tuple(company_ids), date_from, date_to, PL_TYPES),
        )
        return [(r[0], r[1], r[2], float(r[3] or 0.0)) for r in self.env.cr.fetchall()]

    # ------------------------------------------------------------------
    # Classification of accounts into buckets
    # ------------------------------------------------------------------
    def _bucket_resolver(self, account_ids):
        """Bucket of every account with activity: explicit mapping first, then the live
        classifier (so a brand new account is never lost), then the section fallback."""
        Bucket = self.env["ceo.cost.bucket"].sudo()
        buckets = Bucket.search([])
        by_id = {b.id: b for b in buckets}
        by_code = {b.code: b for b in buckets}

        mapping = {}
        for m in self.env["ceo.cost.account.mapping"].sudo().search_fetch([], ["account_id", "bucket_id"]):
            if m.bucket_id.id in by_id:
                mapping[m.account_id.id] = by_id[m.bucket_id.id].code

        accounts = self.env["account.account"].sudo().browse(sorted(account_ids)).exists()
        info = self.env["ceo.cost.account.mapping"]._account_info(accounts)
        types = {a.id: a.account_type for a in accounts}
        resolved, unmapped = {}, 0
        for acc_id in account_ids:
            code = mapping.get(acc_id)
            if not code:
                unmapped += 1
                label = info.get(acc_id, ("", ""))
                code = classify_account(label[0], label[1], types.get(acc_id))
            if code not in by_code:
                code = "REVENUE" if types.get(acc_id) in INCOME_TYPES else "OTHER_OPEX"
            resolved[acc_id] = code

        def bucket_of(acc_id, acc_type=None):
            code = resolved.get(acc_id)
            if code:
                return code
            return "REVENUE" if acc_type in INCOME_TYPES else "OTHER_OPEX"

        return {
            "buckets": buckets,
            "by_code": by_code,
            "bucket_of": bucket_of,
            "info": info,
            "unmapped": unmapped,
            "resolved": resolved,
        }

    # ------------------------------------------------------------------
    # Aggregations
    # ------------------------------------------------------------------
    @staticmethod
    def _signed(acc_type, debit, credit):
        return (credit - debit) if acc_type in INCOME_TYPES else (debit - credit)

    def _aggregate(self, rows, bucket_of, company_set):
        section, bucket, account = defaultdict(float), defaultdict(float), defaultdict(float)
        for acc_id, acc_type, comp_id, debit, credit, *_rest in rows:
            if comp_id not in company_set:
                continue
            amount = self._signed(acc_type, debit, credit)
            section[SECTION_OF_TYPE[acc_type]] += amount
            bucket[bucket_of(acc_id, acc_type)] += amount
            account[acc_id] += amount
        return {"section": section, "bucket": bucket, "account": account}

    @staticmethod
    def _summary(section):
        revenue = section.get("revenue", 0.0)
        cogs = section.get("cogs", 0.0)
        opex = section.get("opex", 0.0)
        other = section.get("other_income", 0.0)
        gross = revenue - cogs
        operating = gross - opex
        net = operating + other
        total_cost = cogs + opex
        return {
            "revenue": revenue,
            "cogs": cogs,
            "gross_profit": gross,
            "gross_margin": _pct(gross, revenue),
            "opex": opex,
            "total_cost": total_cost,
            "operating_profit": operating,
            "operating_margin": _pct(operating, revenue),
            "other_income": other,
            "net_profit": net,
            "net_margin": _pct(net, revenue),
            "cost_ratio": _pct(total_cost, revenue),
        }

    @staticmethod
    def _round_dict(values, decimals):
        return {k: round(v, decimals) if isinstance(v, float) else v for k, v in values.items()}

    def _monthly(self, cube, bucket_of, company_set, date_from, date_to):
        months, cursor = [], date_from.replace(day=1)
        while cursor <= date_to:
            months.append(cursor.strftime("%Y-%m"))
            cursor += relativedelta(months=1)
        data = {m: defaultdict(float) for m in months}
        by_bucket = defaultdict(lambda: defaultdict(float))
        for acc_id, acc_type, comp_id, debit, credit, month in cube:
            if comp_id not in company_set or month not in data:
                continue
            amount = self._signed(acc_type, debit, credit)
            data[month][SECTION_OF_TYPE[acc_type]] += amount
            by_bucket[bucket_of(acc_id, acc_type)][month] += amount
        rows = []
        for m in months:
            s = self._summary(data[m])
            rows.append({
                "month": m,
                "revenue": round(s["revenue"], 3),
                "cost": round(s["total_cost"], 3),
                "other_income": round(s["other_income"], 3),
                "net_profit": round(s["net_profit"], 3),
                "gross_profit": round(s["gross_profit"], 3),
            })
        return {"rows": rows, "by_bucket": by_bucket, "months": months}

    def _bucket_rows(self, buckets, cur, prev, bucket_trend, months, summary, resolver, decimals):
        revenue, total_cost = summary["revenue"], summary["total_cost"]
        accounts_by_bucket = defaultdict(list)
        for acc_id, amount in cur["account"].items():
            accounts_by_bucket[resolver["resolved"].get(acc_id)].append((acc_id, amount))
        rows = []
        for b in buckets.filtered("active"):
            amount = cur["bucket"].get(b.code, 0.0)
            prev_amount = prev["bucket"].get(b.code, 0.0)
            if not amount and not prev_amount:
                continue
            income = b.category_type in ("revenue", "other_income")
            accounts = sorted(accounts_by_bucket.get(b.code, []), key=lambda x: -abs(x[1]))
            rows.append({
                "id": b.id,
                "code": b.code,
                "name": b.name,
                "color": b.color or "#64748b",
                "family": "income" if income else "cost",
                "kind": b.category_type,
                "amount": round(amount, decimals),
                "prev_amount": round(prev_amount, decimals),
                "delta_pct": _delta(amount, prev_amount),
                "pct_revenue": _pct(amount, revenue),
                "share": _pct(amount, revenue if income else total_cost),
                "trend": [round(bucket_trend.get(b.code, {}).get(m, 0.0), decimals) for m in months],
                "account_ids": [a for a, _x in accounts],
                "account_count": len(accounts),
                "accounts": [
                    {
                        "id": a,
                        "code": resolver["info"].get(a, ("", ""))[0],
                        "name": resolver["info"].get(a, ("", ""))[1],
                        "amount": round(v, decimals),
                        "pct": _pct(v, amount),
                    }
                    for a, v in accounts[:12]
                ],
            })
        return rows

    def _platforms(self, account_amounts, resolver, revenue):
        """Cost of every delivery platform = commission (cost bucket) + discount given (revenue adjustment)."""
        res = {}
        for acc_id, amount in account_amounts.items():
            code = resolver["resolved"].get(acc_id)
            if code not in ("DELIVERY", "REV_ADJ"):
                continue
            name = resolver["info"].get(acc_id, ("", ""))[1]
            key = platform_of(name)
            if code == "REV_ADJ" and not key:
                continue
            key = key or "other"
            row = res.setdefault(key, {"commission": 0.0, "discount": 0.0})
            if code == "DELIVERY":
                row["commission"] += amount
            else:
                row["discount"] += -amount  # a discount reduces revenue: show it as a cost
        names = {"other": _("Other / unallocated")}
        names.update({p["key"]: p["name"] for p in load_rules()["platforms"]})
        out = []
        for key, row in res.items():
            total = row["commission"] + row["discount"]
            if not total:
                continue
            out.append({
                "key": key,
                "name": names.get(key, key),
                "commission": round(row["commission"], 3),
                "discount": round(row["discount"], 3),
                "total": round(total, 3),
                "pct_revenue": _pct(total, revenue),
            })
        return sorted(out, key=lambda r: -r["total"])

    def _companies(self, companies, cube_cur, cube_prev, bucket_of, resolver, decimals):
        rows = []
        grand_revenue = 0.0
        data = {}
        for company in companies:
            cid = {company.id}
            cur = self._aggregate(cube_cur, bucket_of, cid)
            prev = self._aggregate(cube_prev, bucket_of, cid)
            s, p = self._summary(cur["section"]), self._summary(prev["section"])
            grand_revenue += s["revenue"]
            data[company.id] = (company, cur, s, p)
        for company, cur, s, p in data.values():
            rows.append({
                "id": company.id,
                "name": company.name,
                "currency": company.currency_id.name,
                "revenue": round(s["revenue"], decimals),
                "cogs": round(s["cogs"], decimals),
                "gross_profit": round(s["gross_profit"], decimals),
                "gross_margin": s["gross_margin"],
                "opex": round(s["opex"], decimals),
                "total_cost": round(s["total_cost"], decimals),
                "operating_profit": round(s["operating_profit"], decimals),
                "other_income": round(s["other_income"], decimals),
                "net_profit": round(s["net_profit"], decimals),
                "net_margin": s["net_margin"],
                "revenue_share": _pct(s["revenue"], grand_revenue),
                "revenue_delta": _delta(s["revenue"], p["revenue"]),
                "net_delta": _delta(s["net_profit"], p["net_profit"]),
                "prev_net_profit": round(p["net_profit"], decimals),
                "buckets": {
                    code: round(v, decimals)
                    for code, v in cur["bucket"].items()
                    if v and resolver["by_code"].get(code) and resolver["by_code"][code].category_type
                    not in ("revenue", "other_income")
                },
                "status": self._status(s["revenue"], s["total_cost"], s["net_profit"], s["net_margin"]),
            })
        return sorted(rows, key=lambda r: -r["revenue"])

    def _status(self, revenue, cost, net, margin):
        if not revenue and not cost:
            return "nodata"
        if net < 0:
            return "loss"
        return "healthy" if margin >= self._param("ecd.branch_healthy_margin") else "watch"

    # ------------------------------------------------------------------
    # Branches & departments (analytic accounts)
    # ------------------------------------------------------------------
    def _analytic_roles(self, analytic_ids):
        roles = {}
        for m in self.env["ceo.cost.analytic.map"].sudo().search([("active", "=", True)]):
            roles[m.analytic_id.id] = {
                "kind": m.kind,
                "short": m.short_name or m.analytic_id.name,
                "region": m.region or "",
                "pos_keywords": m.pos_keywords or "",
                "name": m.analytic_id.name,
            }
        missing = set(analytic_ids) - set(roles)
        if missing:
            for analytic in self.env["account.analytic.account"].sudo().browse(sorted(missing)).exists():
                kind, short, region = classify_analytic(analytic.name)
                roles[analytic.id] = {
                    "kind": kind,
                    "short": short or analytic.name,
                    "region": region,
                    "pos_keywords": short.replace("فرع", "").strip() if kind == "branch" else "",
                    "name": analytic.name,
                }
        return roles

    def _analytic_views(self, company_ids, period, bucket_of, resolver, summary, section, decimals):
        cube = self._fetch_analytic_cube(company_ids, period["date_from"], period["date_to"])
        roles = self._analytic_roles({r[0] for r in cube})

        stats = defaultdict(lambda: {"revenue": 0.0, "other_income": 0.0, "cost": defaultdict(float)})
        for analytic_id, acc_id, acc_type, net in cube:
            if analytic_id not in roles:
                continue
            s = stats[analytic_id]
            section_name = SECTION_OF_TYPE[acc_type]
            if section_name == "revenue":
                s["revenue"] += net
            elif section_name == "other_income":
                s["other_income"] += net
            else:
                s["cost"][bucket_of(acc_id, acc_type)] += -net

        threshold = self._param("ecd.branch_healthy_margin")
        pos_sales = self._pos_sales_by_config(company_ids, period)
        branch_roles = {i: r for i, r in roles.items() if r["kind"] == "branch"}
        pos_by_branch = self._match_pos_to_branches(pos_sales, branch_roles)

        rows = []
        ledger_revenue = ledger_cost = 0.0
        for analytic_id, role in branch_roles.items():
            s = stats.get(analytic_id)
            revenue = s["revenue"] if s else 0.0
            costs = dict(s["cost"]) if s else {}
            total_cost = sum(costs.values())
            other = s["other_income"] if s else 0.0
            pos = pos_by_branch.get(analytic_id, 0.0)
            source = "ledger"
            ledger_revenue += revenue
            ledger_cost += total_cost
            if revenue <= 0 < pos:
                revenue, source = pos, "pos"
            net = revenue + other - total_cost
            margin = _pct(net, revenue)
            rent = costs.get("RENT", 0.0)
            if not revenue and not total_cost:
                status = "nodata"
            elif source == "pos" and not total_cost:
                status = "salesonly"  # sales known from POS, no cost traced to the branch yet
            elif net < 0 or (not revenue and total_cost):
                status = "loss"
            else:
                status = "healthy" if margin >= threshold else "watch"
            rows.append({
                "id": analytic_id,
                "name": role["short"],
                "full_name": role["name"],
                "region": role["region"],
                "revenue": round(revenue, decimals),
                "source": source,
                "pos_sales": round(pos, decimals),
                "cost": round(total_cost, decimals),
                "net_profit": round(net, decimals),
                "net_margin": margin,
                "rent": round(rent, decimals),
                "rent_pct": _pct(rent, revenue),
                "payroll": round(costs.get("PAYROLL", 0.0), decimals),
                "delivery": round(costs.get("DELIVERY", 0.0), decimals),
                "utilities": round(costs.get("UTILITIES", 0.0), decimals),
                "buckets": {k: round(v, decimals) for k, v in costs.items() if v},
                "status": status,
            })
        rows.sort(key=lambda r: (-r["revenue"], r["name"]))

        regions = defaultdict(lambda: {"revenue": 0.0, "net_profit": 0.0, "count": 0, "loss": 0})
        for r in rows:
            reg = regions[r["region"] or ""]
            reg["revenue"] += r["revenue"]
            reg["net_profit"] += r["net_profit"]
            reg["count"] += 1
            reg["loss"] += 1 if r["status"] == "loss" else 0
        counts = defaultdict(int)
        for r in rows:
            counts[r["status"]] += 1

        revenue_total, cost_total = summary["revenue"], summary["total_cost"]
        branches = {
            "rows": rows,
            "counts": {k: counts.get(k, 0) for k in ("healthy", "watch", "loss", "salesonly", "nodata")},
            "regions": sorted(
                (
                    {
                        "region": k,
                        "revenue": round(v["revenue"], decimals),
                        "net_profit": round(v["net_profit"], decimals),
                        "margin": _pct(v["net_profit"], v["revenue"]),
                        "count": v["count"],
                        "loss": v["loss"],
                    }
                    for k, v in regions.items()
                ),
                key=lambda r: r["region"] or "z",
            ),
            "coverage": {
                "revenue_pct": min(_pct(ledger_revenue, revenue_total), 100.0),
                "cost_pct": min(_pct(ledger_cost, cost_total), 100.0),
                "ledger_revenue": round(ledger_revenue, decimals),
                "pos_branches": sum(1 for r in rows if r["source"] == "pos"),
            },
        }

        dept_rows = []
        for analytic_id, role in roles.items():
            if role["kind"] not in ("factory", "department"):
                continue
            s = stats.get(analytic_id)
            if not s:
                continue
            total = sum(s["cost"].values())
            if not total:
                continue
            top = sorted(s["cost"].items(), key=lambda x: -x[1])[:4]
            dept_rows.append({
                "id": analytic_id,
                "name": role["short"],
                "full_name": role["name"],
                "kind": role["kind"],
                "cost": round(total, decimals),
                "top": [{"code": c, "amount": round(v, decimals)} for c, v in top if v],
            })
        dept_rows.sort(key=lambda r: -r["cost"])
        dept_total = sum(r["cost"] for r in dept_rows)
        for r in dept_rows:
            r["share"] = _pct(r["cost"], dept_total)
        departments = {
            "rows": dept_rows,
            "total": round(dept_total, decimals),
            "by_kind": {
                kind: round(sum(r["cost"] for r in dept_rows if r["kind"] == kind), decimals)
                for kind in ("factory", "department")
            },
        }
        return branches, departments

    def _utc_bounds(self, date_from, date_to):
        try:
            tz = pytz.timezone(self.env.context.get("tz") or self.env.user.tz or "UTC")
        except pytz.UnknownTimeZoneError:
            tz = pytz.utc
        start = tz.localize(datetime.combine(date_from, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        end = tz.localize(datetime.combine(date_to, time.max)).astimezone(pytz.utc).replace(tzinfo=None)
        return start, end

    def _pos_sales_by_config(self, company_ids, period):
        """{pos config name: net sales} - empty when Point of Sale is not installed."""
        if "pos.order" not in self.env:
            return {}
        start, end = self._utc_bounds(period["date_from"], period["date_to"])
        groups = self.env["pos.order"].sudo()._read_group(
            [
                ("state", "in", ("paid", "done", "invoiced")),
                ("date_order", ">=", start),
                ("date_order", "<=", end),
                ("company_id", "in", company_ids),
            ],
            ["config_id"],
            ["amount_total:sum", "amount_tax:sum"],
        )
        return {config.name: (total or 0.0) - (tax or 0.0) for config, total, tax in groups if config}

    @staticmethod
    def _match_pos_to_branches(pos_sales, branch_roles):
        result = defaultdict(float)
        prepared = []
        for analytic_id, role in branch_roles.items():
            words = [normalize(w) for w in re.split(r"[,،]", role["pos_keywords"] or "") if normalize(w)]
            if words:
                prepared.append((analytic_id, words))
        for config_name, amount in pos_sales.items():
            norm = normalize(config_name)
            best, best_len = None, 0
            for analytic_id, words in prepared:
                for word in words:
                    if word in norm and len(word) > best_len:
                        best, best_len = analytic_id, len(word)
            if best:
                result[best] += amount
        return result

    # ------------------------------------------------------------------
    # Chairman alerts
    # ------------------------------------------------------------------
    def _alerts(self, s, p, buckets, branches, departments, companies_rows, th, resolver, currency, companies):
        alerts = []

        def add(level, icon, title, text, tab=None, bucket=None):
            alerts.append({"level": level, "icon": icon, "title": title, "text": text, "tab": tab, "bucket": bucket})

        fmt = lambda v: f"{v:,.0f} {currency.symbol or currency.name}"  # noqa: E731
        if s["revenue"] or s["total_cost"]:
            if s["net_profit"] < 0:
                add("danger", "fa-exclamation-triangle", _("The group is running at a net loss"),
                    _("Net result is %(net)s on revenue of %(rev)s.", net=fmt(s["net_profit"]), rev=fmt(s["revenue"])))
            elif s["net_margin"] < 5:
                add("warning", "fa-warning", _("Thin net margin"),
                    _("Net margin is only %(m).1f%% of revenue.", m=s["net_margin"]))
            else:
                add("success", "fa-check-circle", _("Healthy profitability"),
                    _("Net margin is %(m).1f%% on revenue of %(rev)s.", m=s["net_margin"], rev=fmt(s["revenue"])))

        if p["revenue"]:
            change = _delta(s["revenue"], p["revenue"])
            if change is not None and change <= -10:
                add("danger", "fa-line-chart", _("Revenue is down %(c).1f%%", c=abs(change)),
                    _("Revenue fell from %(a)s to %(b)s versus the previous period.", a=fmt(p["revenue"]), b=fmt(s["revenue"])))
            elif change is not None and change >= 10:
                add("success", "fa-line-chart", _("Revenue is up %(c).1f%%", c=change),
                    _("Revenue grew from %(a)s to %(b)s versus the previous period.", a=fmt(p["revenue"]), b=fmt(s["revenue"])))
            gm_shift = s["gross_margin"] - p["gross_margin"]
            if abs(gm_shift) >= 3:
                add("warning" if gm_shift < 0 else "success", "fa-percent",
                    _("Gross margin %(dir)s %(v).1f points", dir=_("dropped") if gm_shift < 0 else _("improved"), v=abs(gm_shift)),
                    _("From %(a).1f%% to %(b).1f%% of revenue.", a=p["gross_margin"], b=s["gross_margin"]))

        by_code = {b["code"]: b for b in buckets}
        rent = by_code.get("RENT")
        if rent and s["revenue"]:
            if rent["pct_revenue"] >= th["rent_danger_pct"]:
                add("danger", "fa-building", _("Rent consumes %(p).1f%% of revenue", p=rent["pct_revenue"]),
                    _("Above the %(t).0f%% ceiling. Review leases and underperforming locations.", t=th["rent_danger_pct"]),
                    tab="costs", bucket="RENT")
            elif rent["pct_revenue"] >= th["rent_warn_pct"]:
                add("warning", "fa-building", _("Rent is %(p).1f%% of revenue", p=rent["pct_revenue"]),
                    _("Above the %(t).0f%% watch level.", t=th["rent_warn_pct"]), tab="costs", bucket="RENT")
        platforms_total = by_code.get("DELIVERY", {}).get("amount", 0.0)
        if s["revenue"] and _pct(platforms_total, s["revenue"]) >= th["delivery_warn_pct"]:
            add("warning", "fa-motorcycle", _("Delivery platforms take %(p).1f%% of revenue", p=_pct(platforms_total, s["revenue"])),
                _("Commissions of %(a)s. Compare platform profitability.", a=fmt(platforms_total)), tab="costs", bucket="DELIVERY")
        loss = by_code.get("LOSS")
        if loss and s["revenue"] and loss["pct_revenue"] >= th["loss_warn_pct"]:
            add("warning", "fa-trash", _("Waste & shrinkage at %(p).1f%% of revenue", p=loss["pct_revenue"]),
                _("Damaged goods, expiry, weight gaps and cash shortages cost %(a)s.", a=fmt(loss["amount"])),
                tab="costs", bucket="LOSS")

        movers = [
            b for b in buckets
            if b["family"] == "cost" and b["prev_amount"] > 0 and b["delta_pct"] is not None
            and b["delta_pct"] >= th["cost_jump_pct"] and (b["amount"] - b["prev_amount"]) >= 0.01 * max(s["total_cost"], 1.0)
        ]
        for b in sorted(movers, key=lambda x: -(x["amount"] - x["prev_amount"]))[:2]:
            add("warning", "fa-arrow-up", _("%(n)s jumped %(p).0f%%", n=b["name"], p=b["delta_pct"]),
                _("From %(a)s to %(b)s versus the previous period.", a=fmt(b["prev_amount"]), b=fmt(b["amount"])),
                tab="costs", bucket=b["code"])

        c = branches["counts"]
        if c["loss"]:
            worst = sorted((r for r in branches["rows"] if r["status"] == "loss"), key=lambda r: r["net_profit"])[:3]
            add("danger", "fa-shopping-basket", _("%(n)s branch(es) operating at a loss", n=c["loss"]),
                _("Weakest: %(names)s.", names=", ".join(r["name"] for r in worst)), tab="branches")
        over = [r for r in branches["rows"] if r["revenue"] and r["rent_pct"] >= th["rent_danger_pct"]]
        if over:
            add("warning", "fa-building-o", _("%(n)s branch(es) pay more than %(t).0f%% of sales as rent", n=len(over), t=th["rent_danger_pct"]),
                _("Highest: %(names)s.", names=", ".join(r["name"] for r in sorted(over, key=lambda r: -r["rent_pct"])[:3])),
                tab="branches")
        cov = branches["coverage"]
        if branches["rows"] and s["revenue"] and cov["revenue_pct"] < 60:
            add("info", "fa-sitemap", _("Branch P&L covers %(p).0f%% of revenue", p=cov["revenue_pct"]),
                _("Tag sales and expense journal items with the branch analytic account to complete the branch view."),
                tab="branches")

        loss_cos = [r for r in companies_rows if r["status"] == "loss"]
        if len(companies_rows) > 1 and loss_cos:
            add("danger", "fa-industry", _("%(n)s company(ies) in loss", n=len(loss_cos)),
                _("%(names)s.", names=", ".join(r["name"] for r in loss_cos)), tab="companies")
        if len({c.currency_id.id for c in companies}) > 1:
            add("info", "fa-exchange", _("Companies use different currencies"),
                _("Amounts are summed as booked, without conversion."))
        return sorted(alerts, key=lambda a: SEVERITY[a["level"]])[:9]
