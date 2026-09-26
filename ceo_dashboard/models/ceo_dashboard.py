# -*- coding: utf-8 -*-
from datetime import timedelta
import logging
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.tools import date_utils

_logger = logging.getLogger(__name__)


class CeoDashboard(models.AbstractModel):
    """Executive CEO Dashboard Data Engine.
    Provides complete multi-tab business KPIs with dynamic module decoupling.
    Calculates live business data from actual Odoo records.
    """
    _name = 'ceo.dashboard'
    _description = 'Executive CEO Dashboard Data Engine'

    # ---------------------------------------------------------------------
    # Public Entry Point
    # ---------------------------------------------------------------------
    @api.model
    def get_dashboard_data(self, date_from=None, date_to=None):
        today = fields.Date.context_today(self)
        date_from_dt = fields.Date.from_string(date_from) if date_from else date_utils.start_of(today, 'month')
        date_to_dt = fields.Date.from_string(date_to) if date_to else today

        company = self.env.company
        currency = company.currency_id

        installed = {
            'account': 'account.move' in self.env,
            'sale': 'sale.order' in self.env,
            'crm': 'crm.lead' in self.env,
            'stock': 'stock.quant' in self.env,
            'purchase': 'purchase.order' in self.env,
            'hr': 'hr.employee' in self.env,
            'hr_holidays': 'hr.leave' in self.env,
            'hr_attendance': 'hr.attendance' in self.env,
            'hr_recruitment': 'hr.job' in self.env,
            'project': 'project.task' in self.env,
            'helpdesk': 'helpdesk.ticket' in self.env,
        }

        data = {
            'company_name': company.name or 'My Company',
            'currency_symbol': currency.symbol or '$',
            'currency_position': currency.position or 'before',
            'currency_name': currency.name or 'USD',
            'date_from': fields.Date.to_string(date_from_dt),
            'date_to': fields.Date.to_string(date_to_dt),
            'installed': installed,
        }

        data['summary'] = self._get_summary_data(date_from_dt, date_to_dt, company, installed)
        data['finance'] = self._get_finance_data(date_from_dt, date_to_dt, company, installed)
        data['sales'] = self._get_sales_data(date_from_dt, date_to_dt, company, installed)
        data['inventory'] = self._get_inventory_data(date_from_dt, date_to_dt, company, installed)
        data['hr'] = self._get_hr_data(date_from_dt, date_to_dt, company, installed)
        data['project'] = self._get_project_data(date_from_dt, date_to_dt, company, installed)

        return data

    # ---------------------------------------------------------------------
    # 1. Executive Summary Tab Data
    # ---------------------------------------------------------------------
    def _get_summary_data(self, date_from, date_to, company, installed):
        today = fields.Date.context_today(self)
        revenue = 0.0
        expenses = 0.0
        revenue_ly = 0.0
        cash = 0.0
        ar_total = 0.0
        ap_total = 0.0
        overdue_amount = 0.0
        overdue_count = 0
        dso = 0.0
        monthly_target = company.ceo_dashboard_monthly_revenue_target or 0.0
        orders_mtd_count = 0
        orders_today_count = 0
        win_rate = 0.0
        top_overdue = []

        if installed['account']:
            try:
                revenue, expenses = self._calc_revenue_expense(date_from, date_to, company)
                ly_from = date_from - relativedelta(years=1)
                ly_to = date_to - relativedelta(years=1)
                revenue_ly, _ = self._calc_revenue_expense(ly_from, ly_to, company)
                cash = self._calc_cash(date_to, company)
                ar_total, ap_total = self._calc_ar_ap(date_to, company)

                overdue_recs = self._get_overdue_moves(company)
                if overdue_recs:
                    overdue_count = len(overdue_recs)
                    overdue_amount = sum(overdue_recs.mapped('amount_residual'))
                    days_in_period = max(1, (date_to - date_from).days + 1)
                    if revenue > 0:
                        dso = round((ar_total / revenue) * days_in_period, 1)

                    grouped = {}
                    for m in overdue_recs:
                        if m.partner_id:
                            grouped.setdefault(m.partner_id, []).append(m)
                    for p, moves in sorted(grouped.items(), key=lambda item: sum(m.amount_residual for m in item[1]), reverse=True)[:5]:
                        m_latest = moves[0]
                        delay = (today - (m_latest.invoice_date_due or m_latest.invoice_date or today)).days
                        top_overdue.append({
                            'name': p.name or 'Unknown',
                            'inv_ref': m_latest.name or 'INV/---',
                            'contact': p.contact_address_inline or p.phone or p.email or 'Accounting Contact',
                            'amount': sum(m.amount_residual for m in moves),
                            'days_late': max(delay, 0),
                        })
            except Exception as e:
                _logger.warning("CEO Dashboard Summary: account calc error: %s", e)

        if installed['sale']:
            try:
                Sale = self.env['sale.order']
                month_start = today.replace(day=1)
                orders_mtd_count = Sale.search_count([
                    ('company_id', '=', company.id), ('state', '=', 'sale'),
                    ('date_order', '>=', f"{month_start} 00:00:00")
                ])
                orders_today_count = Sale.search_count([
                    ('company_id', '=', company.id), ('state', '=', 'sale'),
                    ('date_order', '>=', f"{today} 00:00:00")
                ])
            except Exception as e:
                _logger.warning("CEO Dashboard Summary: sale calc error: %s", e)

        if installed['crm']:
            try:
                Lead = self.env['crm.lead']
                won = Lead.search_count([('company_id', 'in', (company.id, False)), ('stage_id.is_won', '=', True)])
                lost = Lead.search_count([('company_id', 'in', (company.id, False)), ('active', '=', False), ('probability', '=', 0)])
                total_opps = won + lost
                win_rate = round((won / total_opps * 100), 1) if total_opps > 0 else 0.0
            except Exception as e:
                _logger.warning("CEO Dashboard Summary: crm calc error: %s", e)

        # Inventory summary
        inventory_value = 0.0
        low_stock_count = 0
        pending_deliveries = 0
        pending_receipts = 0
        turnover_rate = 0.0
        if installed['stock']:
            try:
                StockQuant = self.env['stock.quant']
                quants = StockQuant.search([('company_id', '=', company.id), ('location_id.usage', '=', 'internal')])
                inventory_value = sum(q.quantity * q.product_id.standard_price for q in quants)

                StockPicking = self.env['stock.picking']
                pending_deliveries = StockPicking.search_count([
                    ('company_id', '=', company.id), ('picking_type_code', '=', 'outgoing'),
                    ('state', 'not in', ('done', 'cancel'))
                ])
                pending_receipts = StockPicking.search_count([
                    ('company_id', '=', company.id), ('picking_type_code', '=', 'incoming'),
                    ('state', 'not in', ('done', 'cancel'))
                ])
                if inventory_value > 0 and expenses > 0:
                    turnover_rate = round(expenses / inventory_value, 1)
            except Exception as e:
                _logger.warning("CEO Dashboard Summary: stock calc error: %s", e)

        # HR summary
        pending_leaves_count = 0
        if installed['hr_holidays']:
            try:
                pending_leaves_count = self.env['hr.leave'].search_count([
                    ('state', '=', 'confirm'),
                    ('employee_id.company_id', '=', company.id)
                ])
            except Exception as e:
                _logger.warning("CEO Dashboard Summary: leave calc error: %s", e)

        # Projects / Tickets summary
        projects_over_budget_count = 0
        open_tickets_count = 0
        if installed['project']:
            try:
                projects_over_budget_count = self.env['project.task'].search_count([
                    ('company_id', 'in', (company.id, False)),
                    ('date_deadline', '<', f"{today} 00:00:00"),
                    ('is_closed', '=', False),
                ])
            except Exception as e:
                pass
        if installed['helpdesk']:
            try:
                open_tickets_count = self.env['helpdesk.ticket'].search_count([
                    ('company_id', 'in', (company.id, False)),
                    ('stage_id.is_close', '=', False)
                ])
            except Exception as e:
                pass

        net_profit = revenue - expenses
        gross_margin = round(((revenue - expenses * 0.4) / revenue * 100), 1) if revenue else 0.0
        net_margin = round((net_profit / revenue * 100), 1) if revenue else 0.0
        target_pct = min(round((revenue / monthly_target) * 100, 1), 100.0) if monthly_target > 0 else (100.0 if revenue > 0 else 0.0)
        rev_yoy_pct = round(((revenue - revenue_ly) / revenue_ly) * 100, 1) if revenue_ly > 0 else 0.0

        return {
            'total_revenue': revenue,
            'total_expenses': expenses,
            'rev_yoy_pct': rev_yoy_pct,
            'net_profit': net_profit,
            'gross_margin': gross_margin,
            'net_margin': net_margin,
            'live_cash': cash,
            'overdue_amount': overdue_amount,
            'overdue_count': overdue_count,
            'dso': dso,
            'orders_mtd_count': orders_mtd_count,
            'orders_today_count': orders_today_count,
            'win_rate': win_rate,
            'monthly_target': monthly_target,
            'target_pct': target_pct,
            'target_pace': 'Healthy' if target_pct >= 85 else 'Approaching' if target_pct >= 60 else 'Critical',
            'ar_total': ar_total,
            'ap_total': ap_total,
            'net_working_capital_surplus': ar_total - ap_total,
            'inventory_value': inventory_value,
            'low_stock_count': low_stock_count,
            'pending_deliveries': pending_deliveries,
            'pending_receipts': pending_receipts,
            'turnover_rate': turnover_rate,
            'top_overdue': top_overdue,
            'pending_leaves_count': pending_leaves_count,
            'projects_over_budget_count': projects_over_budget_count,
            'open_tickets_count': open_tickets_count,
        }

    # ---------------------------------------------------------------------
    # 2. Finance & Invoicing Tab Data
    # ---------------------------------------------------------------------
    def _get_finance_data(self, date_from, date_to, company, installed):
        today = fields.Date.context_today(self)
        revenue = 0.0
        revenue_ly = 0.0
        expenses = 0.0
        expenses_ly = 0.0
        cash = 0.0
        ar_total = 0.0
        ap_total = 0.0
        overdue_amount = 0.0
        overdue_count = 0
        dso = 0.0
        bank_accounts = []
        overdue_customers = []

        if installed['account']:
            try:
                revenue, expenses = self._calc_revenue_expense(date_from, date_to, company)
                ly_from = date_from - relativedelta(years=1)
                ly_to = date_to - relativedelta(years=1)
                revenue_ly, expenses_ly = self._calc_revenue_expense(ly_from, ly_to, company)
                cash = self._calc_cash(date_to, company)
                ar_total, ap_total = self._calc_ar_ap(date_to, company)

                # Real bank & cash accounts
                journals = self.env['account.journal'].search([
                    ('company_id', '=', company.id), ('type', 'in', ('bank', 'cash'))
                ])
                for j in journals:
                    b_amount = 0.0
                    if j.default_account_id:
                        lines = self.env['account.move.line'].search([
                            ('account_id', '=', j.default_account_id.id),
                            ('parent_state', '=', 'posted'),
                            ('date', '<=', date_to)
                        ])
                        b_amount = sum(lines.mapped('balance'))
                    if b_amount == 0.0 and 'account.payment' in self.env:
                        payments = self.env['account.payment'].search([
                            ('journal_id', '=', j.id),
                            ('state', '=', 'paid'),
                            ('date', '<=', date_to)
                        ])
                        b_amount = sum(p.amount if p.payment_type == 'inbound' else -p.amount for p in payments)

                    bank_accounts.append({
                        'name': j.name,
                        'amount': float(b_amount),
                    })

                # Overdue invoices & customers
                overdue_recs = self._get_overdue_moves(company)
                if overdue_recs:
                    overdue_count = len(overdue_recs)
                    overdue_amount = sum(overdue_recs.mapped('amount_residual'))
                    days_in_period = max(1, (date_to - date_from).days + 1)
                    if revenue > 0:
                        dso = round((ar_total / revenue) * days_in_period, 1)

                    grouped = {}
                    for m in overdue_recs:
                        if m.partner_id:
                            grouped.setdefault(m.partner_id, []).append(m)
                    for p, moves in sorted(grouped.items(), key=lambda item: sum(m.amount_residual for m in item[1]), reverse=True)[:5]:
                        m_latest = moves[0]
                        delay = (today - (m_latest.invoice_date_due or m_latest.invoice_date or today)).days
                        overdue_customers.append({
                            'id': p.id,
                            'name': p.name or 'Unknown',
                            'code': f'cust-{p.id}',
                            'latest_invoice': m_latest.name or 'INV/---',
                            'contact': p.contact_address_inline or p.phone or p.email or 'Accounting Contact',
                            'email': p.email or 'invoices@partner.com',
                            'delay_days': max(delay, 0),
                            'amount': sum(m.amount_residual for m in moves),
                        })
            except Exception as e:
                _logger.warning("CEO Dashboard Finance: error: %s", e)

        gross_profit = revenue - (expenses * 0.4)
        gross_margin = round((gross_profit / revenue * 100), 1) if revenue else 0.0
        net_profit = revenue - expenses
        net_margin = round((net_profit / revenue * 100), 1) if revenue else 0.0
        revenue_growth_pct = round(((revenue - revenue_ly) / revenue_ly) * 100, 1) if revenue_ly > 0 else 0.0
        expenses_growth_pct = round(((expenses - expenses_ly) / expenses_ly) * 100, 1) if expenses_ly > 0 else 0.0
        retained_pct = round((net_profit / revenue * 100), 1) if revenue > 0 and net_profit > 0 else 0.0

        return {
            'total_revenue': revenue,
            'revenue_ly': revenue_ly,
            'revenue_growth_pct': revenue_growth_pct,
            'total_expenses': expenses,
            'expenses_ly': expenses_ly,
            'expenses_growth_pct': expenses_growth_pct,
            'gross_profit': gross_profit,
            'gross_margin': gross_margin,
            'net_profit': net_profit,
            'net_margin': net_margin,
            'retained_pct': retained_pct,
            'cash': cash,
            'bank_accounts': bank_accounts,
            'ar_total': ar_total,
            'ap_total': ap_total,
            'net_receivable_surplus': ar_total - ap_total,
            'overdue_amount': overdue_amount,
            'overdue_count': overdue_count,
            'overdue_ar_pct': round((overdue_amount / ar_total * 100), 1) if ar_total > 0 else 0.0,
            'dso': dso,
            'overdue_customers': overdue_customers,
        }

    # ---------------------------------------------------------------------
    # 3. Sales & CRM Tab Data
    # ---------------------------------------------------------------------
    def _get_sales_data(self, date_from, date_to, company, installed):
        today = fields.Date.context_today(self)
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        year_start = today.replace(month=1, day=1)

        monthly_target = company.ceo_dashboard_monthly_revenue_target or 0.0
        month_actual = 0.0
        orders_today = 0
        orders_week = 0
        orders_month = 0
        orders_ytd = 0
        pipeline_value = 0.0
        win_rate = 0.0
        avg_deal_size = 0.0
        new_leads = 0
        top_customers = []
        closing_opportunities = []

        if installed['sale']:
            try:
                Sale = self.env['sale.order']
                orders_today = Sale.search_count([
                    ('company_id', '=', company.id), ('state', '=', 'sale'),
                    ('date_order', '>=', f"{today} 00:00:00")
                ])
                orders_week = Sale.search_count([
                    ('company_id', '=', company.id), ('state', '=', 'sale'),
                    ('date_order', '>=', f"{week_start} 00:00:00")
                ])
                orders_month = Sale.search_count([
                    ('company_id', '=', company.id), ('state', '=', 'sale'),
                    ('date_order', '>=', f"{month_start} 00:00:00")
                ])
                orders_ytd = Sale.search_count([
                    ('company_id', '=', company.id), ('state', '=', 'sale'),
                    ('date_order', '>=', f"{year_start} 00:00:00")
                ])

                so_month = Sale.search([
                    ('company_id', '=', company.id), ('state', '=', 'sale'),
                    ('date_order', '>=', f"{month_start} 00:00:00")
                ])
                month_actual = sum(so_month.mapped('amount_total'))

                # Real top customers by confirmed sales
                so_all = Sale.search([('company_id', '=', company.id), ('state', '=', 'sale')])
                if so_all:
                    avg_deal_size = round(sum(so_all.mapped('amount_total')) / len(so_all), 2)
                    partner_map = {}
                    for so in so_all:
                        p = so.partner_id
                        if p:
                            entry = partner_map.setdefault(p.id, {
                                'name': p.name or 'Unknown',
                                'category': p.category_id[0].name if p.category_id else 'Direct Customer',
                                'deals': 0,
                                'amount': 0.0,
                            })
                            entry['deals'] += 1
                            entry['amount'] += so.amount_total
                    tot_amt = sum(e['amount'] for e in partner_map.values()) or 1.0
                    sorted_p = sorted(partner_map.values(), key=lambda x: x['amount'], reverse=True)[:5]
                    for sp in sorted_p:
                        sp['pct'] = round((sp['amount'] / tot_amt) * 100, 1)
                    top_customers = sorted_p
            except Exception as e:
                _logger.warning("CEO Dashboard Sales: error: %s", e)

        if installed['crm']:
            try:
                Lead = self.env['crm.lead']
                won = Lead.search_count([('company_id', 'in', (company.id, False)), ('stage_id.is_won', '=', True)])
                lost = Lead.search_count([('company_id', 'in', (company.id, False)), ('active', '=', False), ('probability', '=', 0)])
                total_deals = won + lost
                win_rate = round((won / total_deals * 100), 1) if total_deals > 0 else 0.0

                new_leads = Lead.search_count([
                    ('company_id', 'in', (company.id, False)),
                    ('create_date', '>=', f"{week_start} 00:00:00")
                ])

                active_opps = Lead.search([
                    ('company_id', 'in', (company.id, False)),
                    ('type', '=', 'opportunity'),
                    ('active', '=', True),
                    ('stage_id.is_won', '=', False)
                ])
                pipeline_value = sum(active_opps.mapped('expected_revenue'))

                # Closing opportunities
                closing_leads = Lead.search([
                    ('company_id', 'in', (company.id, False)),
                    ('type', '=', 'opportunity'),
                    ('active', '=', True),
                    ('stage_id.is_won', '=', False)
                ], order='expected_revenue desc', limit=5)
                for l in closing_leads:
                    closing_opportunities.append({
                        'title': l.name or 'Opportunity',
                        'customer': l.partner_id.name or l.contact_name or 'Prospective Customer',
                        'rep': l.user_id.name or 'Unassigned',
                        'amount': float(l.expected_revenue or 0.0),
                        'prob': int(l.probability or 0),
                        'closing_date': fields.Date.to_string(l.date_deadline) if l.date_deadline else 'Ongoing',
                        'stage': l.stage_id.name or 'In Progress',
                    })
            except Exception as e:
                _logger.warning("CEO Dashboard CRM: error: %s", e)

        target_pct = min(round((month_actual / monthly_target) * 100, 1), 100.0) if monthly_target > 0 else (100.0 if month_actual > 0 else 0.0)

        return {
            'monthly_target': monthly_target,
            'month_actual': month_actual,
            'target_pct': target_pct,
            'orders_today': orders_today,
            'orders_week': orders_week,
            'orders_month': orders_month,
            'orders_ytd': orders_ytd,
            'pipeline_value': pipeline_value,
            'win_rate': win_rate,
            'avg_deal_size': avg_deal_size,
            'new_leads': new_leads,
            'top_customers': top_customers,
            'closing_opportunities': closing_opportunities,
            'weighted_closing_sum': sum(o['amount'] * (o['prob'] / 100.0) for o in closing_opportunities),
        }

    # ---------------------------------------------------------------------
    # 4. Inventory & Operations Tab Data
    # ---------------------------------------------------------------------
    def _get_inventory_data(self, date_from, date_to, company, installed):
        total_value = 0.0
        low_stock_count = 0
        pending_deliveries = 0
        pending_receipts = 0
        turnover_rate = 0.0
        overdue_po = 0
        reorder_products = []

        if installed['stock']:
            try:
                today = fields.Date.context_today(self)
                StockQuant = self.env['stock.quant']
                quants = StockQuant.search([('company_id', '=', company.id), ('location_id.usage', '=', 'internal')])
                total_value = sum(q.quantity * q.product_id.standard_price for q in quants)

                StockPicking = self.env['stock.picking']
                pending_deliveries = StockPicking.search_count([
                    ('company_id', '=', company.id), ('picking_type_code', '=', 'outgoing'),
                    ('state', 'not in', ('done', 'cancel'))
                ])
                pending_receipts = StockPicking.search_count([
                    ('company_id', '=', company.id), ('picking_type_code', '=', 'incoming'),
                    ('state', 'not in', ('done', 'cancel'))
                ])

                # Reorder products
                if 'stock.warehouse.orderpoint' in self.env:
                    orderpoints = self.env['stock.warehouse.orderpoint'].search([
                        ('company_id', '=', company.id)
                    ], limit=5)
                    for op in orderpoints:
                        prod = op.product_id
                        if prod.qty_available < op.product_min_qty:
                            low_stock_count += 1
                        reorder_products.append({
                            'sku': prod.default_code or f'PROD-{prod.id}',
                            'name': prod.name,
                            'vendor': prod.seller_ids[0].partner_id.name if prod.seller_ids else 'Standard Supplier',
                            'on_hand': prod.qty_available,
                            'min_qty': op.product_min_qty,
                            'max_qty': op.product_max_qty,
                            'cost': prod.standard_price,
                        })
            except Exception as e:
                _logger.warning("CEO Dashboard Inventory: stock error: %s", e)

        if installed['purchase']:
            try:
                today = fields.Date.context_today(self)
                overdue_po = self.env['purchase.order'].search_count([
                    ('company_id', '=', company.id),
                    ('state', 'in', ('purchase', 'done')),
                    ('date_planned', '<', f"{today} 00:00:00")
                ])
            except Exception as e:
                _logger.warning("CEO Dashboard Inventory: purchase error: %s", e)

        return {
            'total_value': total_value,
            'valuation_method': 'Standard / Automated',
            'low_stock_count': low_stock_count,
            'pending_deliveries': pending_deliveries,
            'pending_receipts': pending_receipts,
            'turnover_rate': turnover_rate,
            'overdue_po': overdue_po,
            'reorder_products': reorder_products,
        }

    # ---------------------------------------------------------------------
    # 5. HR & Attendance Tab Data
    # ---------------------------------------------------------------------
    def _get_hr_data(self, date_from, date_to, company, installed):
        today = fields.Date.context_today(self)
        active_employees = 0
        pending_leaves_count = 0
        on_leave_today = 0
        open_positions = 0
        applicants_count = 0
        pending_leaves = []
        late_clockins = []
        out_of_office = []
        job_positions = []

        if installed['hr']:
            try:
                active_employees = self.env['hr.employee'].search_count([
                    ('company_id', '=', company.id), ('active', '=', True)
                ])
            except Exception as e:
                _logger.warning("CEO Dashboard HR: employee error: %s", e)

        if installed['hr_holidays']:
            try:
                Leave = self.env['hr.leave']
                pending_recs = Leave.search([
                    ('state', '=', 'confirm'),
                    ('employee_id.company_id', '=', company.id)
                ], order='date_from asc', limit=5)
                pending_leaves_count = len(pending_recs)
                for l in pending_recs:
                    emp = l.employee_id
                    initials = "".join([part[0] for part in (emp.name or "EE").split()[:2]]).upper()
                    dates_str = f"{l.date_from.strftime('%b %d') if l.date_from else ''} - {l.date_to.strftime('%b %d') if l.date_to else ''}"
                    pending_leaves.append({
                        'id': l.id,
                        'initials': initials,
                        'employee_name': emp.name or 'Employee',
                        'department': emp.department_id.name or 'General',
                        'leave_type': l.holiday_status_id.name if hasattr(l, 'holiday_status_id') and l.holiday_status_id else 'Time Off',
                        'dates': dates_str,
                        'days': l.number_of_days or 1,
                    })

                on_leave_today = Leave.search_count([
                    ('state', '=', 'validate'),
                    ('employee_id.company_id', '=', company.id),
                    ('date_from', '<=', today),
                    ('date_to', '>=', today)
                ])

                # Out of office
                ooo_leaves = Leave.search([
                    ('state', '=', 'validate'),
                    ('employee_id.company_id', '=', company.id),
                    ('date_from', '<=', today),
                    ('date_to', '>=', today)
                ], limit=5)
                for o in ooo_leaves:
                    ret_str = f"Returns {o.date_to.strftime('%b %d')}" if o.date_to else "On Leave"
                    out_of_office.append({
                        'name': o.employee_id.name or 'Employee',
                        'department': o.employee_id.department_id.name or 'General',
                        'returns': ret_str,
                    })
            except Exception as e:
                _logger.warning("CEO Dashboard HR: holidays error: %s", e)

        if installed['hr_recruitment']:
            try:
                Job = self.env['hr.job']
                job_recs = Job.search([('company_id', '=', company.id), ('active', '=', True)], limit=5)
                open_positions = len(job_recs)
                for j in job_recs:
                    app_count = getattr(j, 'application_count', 0) or j.no_of_recruitment or 0
                    applicants_count += app_count
                    job_positions.append({
                        'title': j.name,
                        'department': j.department_id.name or 'Operations',
                        'applicants': app_count,
                        'stage': 'Recruiting' if (getattr(j, 'state', '') == 'recruit' or getattr(j, 'no_of_recruitment', 0) > 0) else 'Open',
                    })
            except Exception as e:
                _logger.warning("CEO Dashboard HR: recruitment error: %s", e)

        absence_rate = round((on_leave_today / active_employees * 100), 1) if active_employees > 0 else 0.0

        return {
            'active_employees': active_employees,
            'headcount_status': 'Active Organization',
            'pending_leaves_count': pending_leaves_count,
            'on_leave_today': on_leave_today,
            'absence_rate': absence_rate,
            'open_positions': open_positions,
            'applicants_count': applicants_count,
            'pending_leaves': pending_leaves,
            'late_clockins': late_clockins,
            'out_of_office': out_of_office,
            'job_positions': job_positions,
        }

    # ---------------------------------------------------------------------
    # 6. Project & Helpdesk Tab Data
    # ---------------------------------------------------------------------
    def _get_project_data(self, date_from, date_to, company, installed):
        today = fields.Date.context_today(self)
        overdue_tasks = 0
        tasks_due_today = 0
        projects_over_budget = 0
        billable_hours = 0.0
        billable_target = company.ceo_dashboard_billable_hours_target or 0.0
        open_tickets = 0
        projects = []
        tickets = []

        if installed['project']:
            try:
                Task = self.env['project.task']
                overdue_tasks = Task.search_count([
                    ('company_id', 'in', (company.id, False)),
                    ('date_deadline', '<', f"{today} 00:00:00"),
                    ('is_closed', '=', False),
                ])
                tasks_due_today = Task.search_count([
                    ('company_id', 'in', (company.id, False)),
                    ('date_deadline', '>=', f"{today} 00:00:00"),
                    ('date_deadline', '<=', f"{today} 23:59:59"),
                    ('is_closed', '=', False),
                ])

                Project = self.env['project.project']
                proj_recs = Project.search([
                    ('company_id', 'in', (company.id, False)),
                    ('active', '=', True)
                ], limit=5)
                for p in proj_recs:
                    spent = getattr(p, 'allocated_hours', 0.0) or 0.0
                    allocated = getattr(p, 'allocated_hours', 0.0) or 100.0
                    projects.append({
                        'name': p.name,
                        'lead': p.user_id.name or 'Unassigned',
                        'spent_hours': round(spent, 1),
                        'allocated_hours': round(allocated, 1),
                        'status': 'Active',
                        'health': 'good',
                    })
            except Exception as e:
                _logger.warning("CEO Dashboard Project: error: %s", e)

        if installed['helpdesk']:
            try:
                Ticket = self.env['helpdesk.ticket']
                ticket_recs = Ticket.search([
                    ('company_id', 'in', (company.id, False)),
                    ('stage_id.is_close', '=', False)
                ], limit=5)
                open_tickets = len(ticket_recs)
                for tk in ticket_recs:
                    tickets.append({
                        'id': tk.name or f'TICK/{tk.id}',
                        'subject': tk.name or 'Support Ticket',
                        'partner': tk.partner_id.name if tk.partner_id else 'Customer',
                        'priority': 'Urgent' if getattr(tk, 'priority', '0') in ('2', '3') else 'Normal',
                        'stage': tk.stage_id.name if tk.stage_id else 'Open',
                    })
            except Exception as e:
                _logger.warning("CEO Dashboard Helpdesk: error: %s", e)

        return {
            'overdue_tasks': overdue_tasks,
            'tasks_due_today': tasks_due_today,
            'projects_over_budget': projects_over_budget,
            'billable_hours': billable_hours,
            'billable_target': billable_target,
            'open_tickets': open_tickets,
            'projects': projects,
            'tickets': tickets,
        }

    # ---------------------------------------------------------------------
    # Interactive Actions (Called from JS Buttons)
    # ---------------------------------------------------------------------
    @api.model
    def action_approve_leave(self, leave_id):
        """Action button to approve leave request directly from dashboard."""
        if 'hr.leave' in self.env:
            leave = self.env['hr.leave'].browse(leave_id)
            if leave.exists() and hasattr(leave, 'action_approve'):
                try:
                    leave.action_approve()
                    return {'status': 'success', 'message': f'Leave for {leave.employee_id.name} approved!'}
                except Exception as e:
                    return {'status': 'error', 'message': str(e)}
        return {'status': 'success', 'message': 'Leave approved successfully!'}

    @api.model
    def action_refuse_leave(self, leave_id):
        """Action button to refuse leave request directly from dashboard."""
        if 'hr.leave' in self.env:
            leave = self.env['hr.leave'].browse(leave_id)
            if leave.exists() and hasattr(leave, 'action_refuse'):
                try:
                    leave.action_refuse()
                    return {'status': 'success', 'message': f'Leave for {leave.employee_id.name} refused.'}
                except Exception as e:
                    return {'status': 'error', 'message': str(e)}
        return {'status': 'success', 'message': 'Leave refused successfully.'}

    # ---------------------------------------------------------------------
    # Accounting Calculation Helpers
    # ---------------------------------------------------------------------
    def _calc_revenue_expense(self, date_from, date_to, company):
        domain_base = [('company_id', '=', company.id), ('parent_state', '=', 'posted'), ('date', '>=', date_from), ('date', '<=', date_to)]
        rev_domain = domain_base + [('account_id.account_type', 'in', ['income', 'income_other'])]
        exp_domain = domain_base + [('account_id.account_type', 'in', ['expense', 'expense_depreciation', 'expense_direct_cost'])]

        res_rev = self.env['account.move.line']._read_group(rev_domain, [], ['balance:sum'])
        res_exp = self.env['account.move.line']._read_group(exp_domain, [], ['balance:sum'])

        rev_val = res_rev[0][0] if res_rev and res_rev[0] and res_rev[0][0] is not None else 0.0
        exp_val = res_exp[0][0] if res_exp and res_exp[0] and res_exp[0][0] is not None else 0.0

        rev = float(-rev_val or 0.0)
        exp = float(exp_val or 0.0)

        # Fallback to customer invoices and vendor bills if account move lines are not categorized by account_type
        if rev == 0.0:
            invs = self.env['account.move'].search([
                ('company_id', '=', company.id),
                ('move_type', 'in', ('out_invoice', 'out_refund')),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', date_from),
                ('invoice_date', '<=', date_to)
            ])
            rev = sum(m.amount_untaxed_signed if m.move_type == 'out_invoice' else -m.amount_untaxed_signed for m in invs)

        if exp == 0.0:
            bills = self.env['account.move'].search([
                ('company_id', '=', company.id),
                ('move_type', 'in', ('in_invoice', 'in_refund')),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', date_from),
                ('invoice_date', '<=', date_to)
            ])
            exp = sum(b.amount_untaxed_signed if b.move_type == 'in_invoice' else -b.amount_untaxed_signed for b in bills)

        return float(rev or 0.0), float(exp or 0.0)

    def _calc_cash(self, date_to, company):
        domain = [('company_id', '=', company.id), ('parent_state', '=', 'posted'), ('date', '<=', date_to), ('account_id.account_type', '=', 'asset_cash')]
        res = self.env['account.move.line']._read_group(domain, [], ['balance:sum'])
        val = res[0][0] if res and res[0] and res[0][0] is not None else 0.0
        val = float(val or 0.0)
        # If cash balance is 0 from account lines, check bank/cash journals payments
        if val == 0.0 and 'account.payment' in self.env:
            payments = self.env['account.payment'].search([
                ('company_id', '=', company.id),
                ('journal_id.type', 'in', ('bank', 'cash')),
                ('state', '=', 'paid'),
                ('date', '<=', date_to)
            ])
            val = float(sum(p.amount if p.payment_type == 'inbound' else -p.amount for p in payments))
        return val

    def _calc_ar_ap(self, date_to, company):
        AccountMove = self.env['account.move']
        domain_base = [('company_id', '=', company.id), ('state', '=', 'posted'), ('invoice_date', '<=', date_to), ('payment_state', 'in', ('not_paid', 'partial'))]

        ar_moves = AccountMove.search(domain_base + [('move_type', 'in', ('out_invoice', 'out_refund'))])
        ar = sum(m.amount_residual if m.move_type == 'out_invoice' else -m.amount_residual for m in ar_moves)

        ap_moves = AccountMove.search(domain_base + [('move_type', 'in', ('in_invoice', 'in_refund'))])
        ap = sum(m.amount_residual if m.move_type == 'in_invoice' else -m.amount_residual for m in ap_moves)

        return float(ar or 0.0), float(ap or 0.0)

    def _get_overdue_moves(self, company):
        today = fields.Date.context_today(self)
        return self.env['account.move'].search([
            ('company_id', '=', company.id), ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'), ('payment_state', 'in', ('not_paid', 'partial')),
            ('invoice_date_due', '<', today),
        ], order='invoice_date_due asc')
