# -*- coding: utf-8 -*-
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from odoo import models, api, fields, _

class CeoCostDashboardReport(models.AbstractModel):
    _name = "ceo.cost.dashboard.report"
    _description = "CEO Financial & Cost Intelligence Engine"

    @api.model
    def get_executive_dashboard_data(self, filters=None):
        if not filters:
            filters = {}

        # 0. Auto-run Smart Scanner on first run if no mappings exist
        mapping_count = self.env["ceo.cost.account.mapping"].search_count([])
        if mapping_count == 0:
            try:
                self.env["ceo.smart.scanner.wizard"].create({}).action_run_smart_scan()
            except Exception:
                pass

        today = fields.Date.context_today(self)
        period_mode = filters.get("period_mode", "this_month")
        
        # Calculate Date Range
        if period_mode == "this_month":
            date_from = today.replace(day=1)
            date_to = (date_from + relativedelta(months=1)) - relativedelta(days=1)
        elif period_mode == "last_month":
            date_to = today.replace(day=1) - relativedelta(days=1)
            date_from = date_to.replace(day=1)
        elif period_mode == "qtd":
            quarter_month = ((today.month - 1) // 3) * 3 + 1
            date_from = today.replace(month=quarter_month, day=1)
            date_to = (date_from + relativedelta(months=3)) - relativedelta(days=1)
        elif period_mode == "ytd":
            date_from = today.replace(month=1, day=1)
            date_to = today
        elif period_mode == "year_2026":
            date_from = date(2026, 1, 1)
            date_to = date(2026, 12, 31)
        else:
            date_from = fields.Date.from_string(filters.get("date_from")) or today.replace(day=1)
            date_to = fields.Date.from_string(filters.get("date_to")) or today

        company_id = int(filters.get("company_id") or 0)
        branch_id = int(filters.get("branch_id") or 0)

        # 1. Fetch Companies & Branches
        Company = self.env["res.company"]
        all_companies = Company.search([])
        
        # Identify parent holding vs operating sister companies vs branches
        holding_company = all_companies.filtered(lambda c: not c.parent_id)[:1] or self.env.company
        sister_companies = all_companies.filtered(lambda c: c.parent_id == holding_company or not c.parent_id)
        if not sister_companies:
            sister_companies = all_companies

        branches = all_companies.filtered(lambda c: c.parent_id in sister_companies or c.parent_id)
        if not branches:
            branches = all_companies

        # Build SQL company filter clause
        where_company = []
        if branch_id:
            where_company.append(f"aml.company_id = {branch_id}")
        elif company_id:
            child_ids = Company.search([("id", "child_of", company_id)]).ids
            where_company.append(f"aml.company_id IN ({','.join(map(str, child_ids))})")

        comp_clause = f"AND {' AND '.join(where_company)}" if where_company else ""

        # 2. Main Financial Aggregation by Bucket (Direct SQL via index)
        query = f"""
            SELECT 
                b.code AS bucket_code,
                b.name AS bucket_name,
                b.category_type,
                b.color,
                b.sequence,
                SUM(aml.credit - aml.debit) AS net_balance,
                SUM(aml.debit) AS total_debit,
                SUM(aml.credit) AS total_credit
            FROM account_move_line aml
            JOIN ceo_cost_account_mapping m_map ON aml.account_id = m_map.account_id
            JOIN ceo_cost_bucket b ON m_map.bucket_id = b.id
            WHERE aml.parent_state = 'posted'
              AND aml.date >= %s AND aml.date <= %s
              {comp_clause}
            GROUP BY b.code, b.name, b.category_type, b.color, b.sequence
            ORDER BY b.sequence
        """
        self.env.cr.execute(query, (date_from, date_to))
        bucket_rows = self.env.cr.dictfetchall()

        buckets_dict = {}
        total_revenue = 0.0
        total_cogs = 0.0
        total_opex = 0.0

        for r in bucket_rows:
            b_code = r["bucket_code"]
            b_type = r["category_type"]
            net_bal = float(r["net_balance"] or 0.0)
            debit = float(r["total_debit"] or 0.0)
            credit = float(r["total_credit"] or 0.0)

            if b_type == "revenue":
                amt = net_bal  # Credit is positive revenue
                total_revenue += amt
            elif b_type == "cogs":
                amt = debit - credit  # Debit is positive cost
                total_cogs += amt
            else:
                amt = debit - credit  # OpEx debit is positive expense
                total_opex += amt

            buckets_dict[b_code] = {
                "code": b_code,
                "name": r["bucket_name"],
                "type": b_type,
                "color": r["color"],
                "amount": round(amt, 3),
            }

        # Safe Margins
        gross_profit = total_revenue - total_cogs
        gross_margin_pct = round((gross_profit / total_revenue * 100), 2) if total_revenue > 0 else 0.0
        net_profit = gross_profit - total_opex
        net_margin_pct = round((net_profit / total_revenue * 100), 2) if total_revenue > 0 else 0.0

        # Specific CEO Focus Buckets
        rent_amt = buckets_dict.get("RENT", {}).get("amount", 0.0)
        utilities_amt = buckets_dict.get("UTILITIES", {}).get("amount", 0.0)
        tech_amt = buckets_dict.get("TECH", {}).get("amount", 0.0)
        payroll_amt = buckets_dict.get("PAYROLL", {}).get("amount", 0.0)
        delivery_amt = buckets_dict.get("DELIVERY", {}).get("amount", 0.0)
        fleet_amt = buckets_dict.get("FLEET", {}).get("amount", 0.0)
        security_amt = buckets_dict.get("SECURITY", {}).get("amount", 0.0)
        maint_amt = buckets_dict.get("MAINTENANCE", {}).get("amount", 0.0)
        loss_amt = buckets_dict.get("LOSS", {}).get("amount", 0.0)

        rent_pct = round((rent_amt / total_revenue * 100), 2) if total_revenue > 0 else 0.0
        utilities_pct = round((utilities_amt / total_revenue * 100), 2) if total_revenue > 0 else 0.0
        delivery_pct = round((delivery_amt / total_revenue * 100), 2) if total_revenue > 0 else 0.0
        tech_pct = round((tech_amt / total_revenue * 100), 2) if total_revenue > 0 else 0.0

        # 3. Sister Companies Breakdown (Anabtawi, United, Alhadaf, Najeed)
        comp_query = f"""
            SELECT 
                c.id AS company_id,
                c.name AS company_name,
                COALESCE(SUM(CASE WHEN b.category_type = 'revenue' THEN (aml.credit - aml.debit) ELSE 0 END), 0) AS revenue,
                COALESCE(SUM(CASE WHEN b.category_type = 'cogs' THEN (aml.debit - aml.credit) ELSE 0 END), 0) AS cogs,
                COALESCE(SUM(CASE WHEN b.category_type = 'expense' THEN (aml.debit - aml.credit) ELSE 0 END), 0) AS opex
            FROM res_company c
            LEFT JOIN account_move_line aml ON aml.company_id = c.id AND aml.parent_state = 'posted' AND aml.date >= %s AND aml.date <= %s
            LEFT JOIN ceo_cost_account_mapping m_map ON aml.account_id = m_map.account_id
            LEFT JOIN ceo_cost_bucket b ON m_map.bucket_id = b.id
            GROUP BY c.id, c.name
            ORDER BY revenue DESC
        """
        self.env.cr.execute(comp_query, (date_from, date_to))
        sister_comp_rows = self.env.cr.dictfetchall()

        sister_companies_list = []
        for sc in sister_comp_rows:
            rev = round(float(sc["revenue"] or 0.0), 3)
            cogs = round(float(sc["cogs"] or 0.0), 3)
            op = round(float(sc["opex"] or 0.0), 3)
            gp = rev - cogs
            np = gp - op
            nm_pct = round((np / rev * 100), 2) if rev > 0 else 0.0
            
            if np > 0:
                status = "profitable"
            elif np == 0:
                status = "break_even"
            else:
                status = "loss"

            sister_companies_list.append({
                "company_id": sc["company_id"],
                "company_name": sc["company_name"],
                "revenue": rev,
                "cogs": cogs,
                "gross_profit": gp,
                "opex": op,
                "net_profit": np,
                "net_margin_pct": nm_pct,
                "status": status,
            })

        # 4. Department Breakdown (Analytic Accounting) - Safe ORM Name Resolution
        analytic_query = """
            SELECT 
                aal.account_id,
                SUM(ABS(aal.amount)) AS total_amount
            FROM account_analytic_line aal
            WHERE aal.amount < 0
              AND aal.date >= %s AND aal.date <= %s
            GROUP BY aal.account_id
            ORDER BY total_amount DESC
            LIMIT 15
        """
        self.env.cr.execute(analytic_query, (date_from, date_to))
        dept_rows = self.env.cr.dictfetchall()

        acc_ids = [r["account_id"] for r in dept_rows if r.get("account_id")]
        accounts_map = {a.id: a.display_name for a in self.env["account.analytic.account"].browse(acc_ids)}

        departments_list = []
        for d in dept_rows:
            acc_id = d.get("account_id")
            dept_name = accounts_map.get(acc_id) or _("General / Operations")
            departments_list.append({
                "name": dept_name,
                "amount": round(float(d["total_amount"] or 0.0), 3),
            })

        # 5. 21-Branch Matrix & Leaderboard
        branch_query = f"""
            SELECT 
                c.id AS branch_id,
                c.name AS branch_name,
                COALESCE(SUM(CASE WHEN b.code = 'REVENUE' THEN (aml.credit - aml.debit) ELSE 0 END), 0) AS revenue,
                COALESCE(SUM(CASE WHEN b.code = 'RENT' THEN (aml.debit - aml.credit) ELSE 0 END), 0) AS rent,
                COALESCE(SUM(CASE WHEN b.code = 'UTILITIES' THEN (aml.debit - aml.credit) ELSE 0 END), 0) AS utilities,
                COALESCE(SUM(CASE WHEN b.code = 'PAYROLL' THEN (aml.debit - aml.credit) ELSE 0 END), 0) AS payroll,
                COALESCE(SUM(CASE WHEN b.code = 'TECH' THEN (aml.debit - aml.credit) ELSE 0 END), 0) AS tech,
                COALESCE(SUM(CASE WHEN b.code = 'DELIVERY' THEN (aml.debit - aml.credit) ELSE 0 END), 0) AS delivery_comm,
                COALESCE(SUM(CASE WHEN b.code IN ('SECURITY', 'MAINTENANCE') THEN (aml.debit - aml.credit) ELSE 0 END), 0) AS maint_security,
                COALESCE(SUM(CASE WHEN b.category_type = 'expense' THEN (aml.debit - aml.credit) ELSE 0 END), 0) AS total_opex
            FROM res_company c
            LEFT JOIN account_move_line aml ON aml.company_id = c.id AND aml.parent_state = 'posted' AND aml.date >= %s AND aml.date <= %s
            LEFT JOIN ceo_cost_account_mapping m_map ON aml.account_id = m_map.account_id
            LEFT JOIN ceo_cost_bucket b ON m_map.bucket_id = b.id
            GROUP BY c.id, c.name
            ORDER BY revenue DESC
        """
        self.env.cr.execute(branch_query, (date_from, date_to))
        branch_rows = self.env.cr.dictfetchall()

        branch_matrix = []
        profitable_branches = 0
        loss_branches = 0

        for br in branch_rows:
            b_rev = round(float(br["revenue"] or 0.0), 3)
            b_rent = round(float(br["rent"] or 0.0), 3)
            b_util = round(float(br["utilities"] or 0.0), 3)
            b_pay = round(float(br["payroll"] or 0.0), 3)
            b_tech = round(float(br["tech"] or 0.0), 3)
            b_deliv = round(float(br["delivery_comm"] or 0.0), 3)
            b_ms = round(float(br["maint_security"] or 0.0), 3)
            b_opex = round(float(br["total_opex"] or 0.0), 3)
            
            b_net_profit = b_rev - b_opex
            b_margin_pct = round((b_net_profit / b_rev * 100), 2) if b_rev > 0 else 0.0
            b_rent_pct = round((b_rent / b_rev * 100), 2) if b_rev > 0 else 0.0

            if b_net_profit > 0 and b_margin_pct >= 10:
                b_status = "profitable"
                profitable_branches += 1
            elif b_net_profit >= 0:
                b_status = "warning"
                profitable_branches += 1
            else:
                b_status = "loss"
                loss_branches += 1

            branch_matrix.append({
                "branch_id": br["branch_id"],
                "branch_name": br["branch_name"],
                "revenue": b_rev,
                "rent": b_rent,
                "rent_pct": b_rent_pct,
                "utilities": b_util,
                "payroll": b_pay,
                "tech": b_tech,
                "delivery_comm": b_deliv,
                "maint_security": b_ms,
                "total_opex": b_opex,
                "net_profit": b_net_profit,
                "net_margin_pct": b_margin_pct,
                "status": b_status,
            })

        # 6. Monthly 12-Month Run-Rate Trend (Last 12 Months)
        trend_query = f"""
            SELECT 
                TO_CHAR(aml.date, 'YYYY-MM') AS month_key,
                COALESCE(SUM(CASE WHEN b.category_type = 'revenue' THEN (aml.credit - aml.debit) ELSE 0 END), 0) AS revenue,
                COALESCE(SUM(CASE WHEN b.category_type = 'expense' THEN (aml.debit - aml.credit) ELSE 0 END), 0) AS opex
            FROM account_move_line aml
            JOIN ceo_cost_account_mapping m_map ON aml.account_id = m_map.account_id
            JOIN ceo_cost_bucket b ON m_map.bucket_id = b.id
            WHERE aml.parent_state = 'posted'
              AND aml.date >= %s
              {comp_clause}
            GROUP BY TO_CHAR(aml.date, 'YYYY-MM')
            ORDER BY month_key ASC
            LIMIT 12
        """
        twelve_months_ago = today - relativedelta(months=11)
        self.env.cr.execute(trend_query, (twelve_months_ago.replace(day=1),))
        trend_rows = self.env.cr.dictfetchall()

        monthly_trend = []
        for t in trend_rows:
            t_rev = round(float(t["revenue"] or 0.0), 3)
            t_op = round(float(t["opex"] or 0.0), 3)
            monthly_trend.append({
                "month": t["month_key"],
                "revenue": t_rev,
                "opex": t_op,
                "net_profit": round(t_rev - t_op, 3),
            })

        # Currency Information
        currency = self.env.company.currency_id
        currency_info = {
            "name": currency.name or "JOD",
            "symbol": currency.symbol or "د.أ",
        }

        return {
            "period": {
                "mode": period_mode,
                "date_from": str(date_from),
                "date_to": str(date_to),
            },
            "currency": currency_info,
            "kpis": {
                "total_revenue": round(total_revenue, 3),
                "gross_profit": round(gross_profit, 3),
                "gross_margin_pct": gross_margin_pct,
                "total_opex": round(total_opex, 3),
                "net_profit": round(net_profit, 3),
                "net_margin_pct": net_margin_pct,
                "rent_amount": round(rent_amt, 3),
                "rent_pct": rent_pct,
                "utilities_amount": round(utilities_amt, 3),
                "utilities_pct": utilities_pct,
                "tech_amount": round(tech_amt, 3),
                "tech_pct": tech_pct,
                "payroll_amount": round(payroll_amt, 3),
                "delivery_amount": round(delivery_amt, 3),
                "delivery_pct": delivery_pct,
                "active_branches_count": len(branch_rows),
                "profitable_branches_count": profitable_branches,
                "loss_branches_count": loss_branches,
            },
            "buckets": list(buckets_dict.values()),
            "sister_companies": sister_companies_list,
            "departments": departments_list,
            "branches": branch_matrix,
            "monthly_trend": monthly_trend,
            "all_companies": [{"id": c.id, "name": c.name} for c in all_companies],
        }
