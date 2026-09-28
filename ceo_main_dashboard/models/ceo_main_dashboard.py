# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from odoo.tools import SQL

TREND_ORDER = {'up': 0, 'down': 0, 'same': 1, 'new': 2}


class CeoMainDashboard(models.AbstractModel):
    """Data engine of the CEO Main Dashboard.

    Purchase prices are compared per product on confirmed purchase order lines,
    normalized to the product's base unit of measure, discount included, and
    converted to the company currency with the rate stored on the order.
    """
    _name = 'ceo.main.dashboard'
    _description = 'CEO Main Dashboard'

    _SEARCH_PRODUCT_LIMIT = 200
    _HISTORY_LIMIT = 12
    _RECENT_ORDERS_LIMIT = 10

    # ---------------------------------------------------------------------
    # Public entry points (called from the OWL client action)
    # ---------------------------------------------------------------------
    @api.model
    def get_purchase_dashboard(self, date_from=None, date_to=None):
        self._check_dashboard_access()
        date_from, date_to = self._parse_range(date_from, date_to)
        company = self.env.company
        currency = company.currency_id
        start, end = self._utc_bounds(date_from, date_to)

        rows, impact = self._get_period_price_comparison(company, date_from, date_to)
        orders = self._confirmed_orders(company, date_from, date_to)

        return {
            'company_name': company.name,
            'currency': {
                'symbol': currency.symbol or '',
                'position': currency.position or 'before',
                'name': currency.name or '',
                'decimals': currency.decimal_places,
            },
            'date_from': fields.Date.to_string(date_from),
            'date_to': fields.Date.to_string(date_to),
            'utc_from': fields.Datetime.to_string(start),
            'utc_to': fields.Datetime.to_string(end),
            'summary': self._get_purchase_summary(company, orders, date_from, date_to),
            'impact': impact,
            'price_rows': rows,
            'daily': self._get_daily_totals(orders, date_from, date_to),
            'recent_orders': self._get_recent_orders(orders),
        }

    @api.model
    def search_purchase_prices(self, term, date_to=None):
        """Latest vs previous purchase price of matching products, whole history up to date_to."""
        self._check_dashboard_access()
        term = (term or '').strip()
        if not term:
            return []
        company = self.env.company
        _dummy, date_to = self._parse_range(date_to, date_to)
        products = self.env['product.product'].sudo().search([
            ('company_id', 'in', (company.id, False)),
            '|', '|',
            ('name', 'ilike', term),
            ('default_code', 'ilike', term),
            ('barcode', 'ilike', term),
        ], limit=self._SEARCH_PRODUCT_LIMIT)
        if not products:
            return []

        _start, end = self._utc_bounds(date_to, date_to)
        fetched = self._fetch_price_lines(company, end, products.ids, SQL("hist.rn = 1"))
        lines = self._browse_lines(fetched)
        rows = [
            self._build_row(lines[line_id], lines[prev_id] if prev_id else None, company.currency_id)
            for line_id, _product_id, prev_id, _rn in fetched
        ]
        return self._sort_rows(rows)

    @api.model
    def get_product_price_history(self, product_id, date_to=None):
        """Last purchases of one product, oldest first, with the change vs the purchase before."""
        self._check_dashboard_access()
        company = self.env.company
        _dummy, date_to = self._parse_range(date_to, date_to)
        _start, end = self._utc_bounds(date_to, date_to)
        fetched = self._fetch_price_lines(
            company, end, [product_id], SQL("hist.rn <= %s", self._HISTORY_LIMIT),
        )
        lines = self._browse_lines(fetched)
        currency = company.currency_id

        history = []
        for line_id, _product_id, prev_id, _rn in reversed(fetched):
            line = lines[line_id]
            row = self._build_row(line, lines[prev_id] if prev_id else None, currency)
            history.append({
                'line_id': line.id,
                'order_id': line.order_id.id,
                'order_name': line.order_id.name,
                'vendor': line.order_id.partner_id.display_name,
                'date': row['last_date'],
                'qty': row['last_qty'],
                'uom': row['uom'],
                'price': row['last_price'],
                'diff': row['diff'],
                'pct': row['pct'],
                'trend': row['trend'],
            })
        return history

    # ---------------------------------------------------------------------
    # Summary, daily totals and recent orders
    # ---------------------------------------------------------------------
    def _get_purchase_summary(self, company, orders, date_from, date_to):
        today = fields.Date.context_today(self)
        yesterday = today - timedelta(days=1)
        span = date_to - date_from
        prev_to = date_from - timedelta(days=1)
        prev_from = prev_to - span

        period_total = sum(orders.mapped('amount_total_cc'))
        prev_total = sum(self._confirmed_orders(company, prev_from, prev_to).mapped('amount_total_cc'))
        today_orders = self._confirmed_orders(company, today, today)
        today_total = sum(today_orders.mapped('amount_total_cc'))
        yesterday_total = sum(self._confirmed_orders(company, yesterday, yesterday).mapped('amount_total_cc'))

        return {
            'period_total': period_total,
            'period_count': len(orders),
            'prev_period_total': prev_total,
            'prev_period_from': fields.Date.to_string(prev_from),
            'prev_period_to': fields.Date.to_string(prev_to),
            'period_change_pct': self._pct_change(period_total, prev_total),
            'vendor_count': len(orders.partner_id),
            'avg_order': period_total / len(orders) if orders else 0.0,
            'today_total': today_total,
            'today_count': len(today_orders),
            'yesterday_total': yesterday_total,
            'today_change_pct': self._pct_change(today_total, yesterday_total),
        }

    def _get_daily_totals(self, orders, date_from, date_to):
        by_month = (date_to - date_from).days > 62
        tz = self._user_tz()
        buckets = defaultdict(lambda: {'amount': 0.0, 'count': 0})
        for order in orders:
            local_date = pytz.utc.localize(order.date_approve).astimezone(tz).date()
            key = local_date.replace(day=1) if by_month else local_date
            buckets[key]['amount'] += order.amount_total_cc
            buckets[key]['count'] += 1

        keys = []
        cursor = date_from.replace(day=1) if by_month else date_from
        while cursor <= date_to:
            keys.append(cursor)
            if by_month:
                cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
            else:
                cursor += timedelta(days=1)

        max_amount = max((b['amount'] for b in buckets.values()), default=0.0)
        return {
            'granularity': 'month' if by_month else 'day',
            'max_amount': max_amount,
            'points': [{
                'date': fields.Date.to_string(key),
                'amount': buckets[key]['amount'],
                'count': buckets[key]['count'],
            } for key in keys],
        }

    def _get_recent_orders(self, orders):
        tz = self._user_tz()
        return [{
            'id': order.id,
            'name': order.name,
            'vendor': order.partner_id.display_name,
            'amount': order.amount_total_cc,
            'date': fields.Datetime.to_string(pytz.utc.localize(order.date_approve).astimezone(tz).replace(tzinfo=None)),
            'buyer': order.user_id.name or '',
            'line_count': len(order.order_line.filtered(lambda l: not l.display_type)),
        } for order in orders[:self._RECENT_ORDERS_LIMIT]]

    # ---------------------------------------------------------------------
    # Price comparison
    # ---------------------------------------------------------------------
    def _get_period_price_comparison(self, company, date_from, date_to):
        """One row per product bought in the period (its latest purchase vs the one before),
        plus the money impact of every price change that happened in the period."""
        currency = company.currency_id
        start, end = self._utc_bounds(date_from, date_to)
        impact = {
            'extra_paid': 0.0, 'saved': 0.0, 'net': 0.0,
            'up_count': 0, 'down_count': 0, 'same_count': 0, 'new_count': 0, 'product_count': 0,
        }

        groups = self.env['purchase.order.line'].sudo()._read_group(
            self._period_line_domain(company, start, end), ['product_id'],
        )
        product_ids = [product.id for product, in groups]
        if not product_ids:
            return [], impact

        fetched = self._fetch_price_lines(company, end, product_ids, SQL("hist.date_approve >= %s", start))
        lines = self._browse_lines(fetched)

        product_impact = defaultdict(float)
        latest = {}
        for line_id, product_id, prev_id, rn in fetched:
            if prev_id:
                line = lines[line_id]
                diff = self._unit_price(line) - self._unit_price(lines[prev_id])
                if not currency.is_zero(diff):
                    amount = diff * line.product_uom_qty
                    product_impact[product_id] += amount
                    impact['extra_paid' if amount > 0 else 'saved'] += abs(amount)
            if rn == 1:
                latest[product_id] = (line_id, prev_id)

        rows = []
        for product_id, (line_id, prev_id) in latest.items():
            row = self._build_row(lines[line_id], lines[prev_id] if prev_id else None, currency)
            row['impact'] = product_impact.get(product_id, 0.0)
            impact[f"{row['trend']}_count"] += 1
            rows.append(row)

        impact['net'] = impact['extra_paid'] - impact['saved']
        impact['product_count'] = len(rows)
        return self._sort_rows(rows), impact

    def _fetch_price_lines(self, company, end, product_ids, outer_condition):
        """Return (line_id, product_id, previous_line_id, rank) of confirmed purchase lines up to `end`.

        `previous_line_id` is the purchase of the same product right before the line (any vendor),
        `rank` is 1 for the most recent purchase of the product.
        """
        self.env['purchase.order'].flush_model(['state', 'company_id', 'date_approve'])
        self.env['purchase.order.line'].flush_model(['order_id', 'product_id', 'display_type', 'is_downpayment'])
        self.env.cr.execute(SQL(
            """
            WITH hist AS (
                SELECT pol.id,
                       pol.product_id,
                       po.date_approve,
                       LAG(pol.id) OVER w_asc AS prev_id,
                       ROW_NUMBER() OVER w_desc AS rn
                  FROM purchase_order_line pol
                  JOIN purchase_order po ON po.id = pol.order_id
                 WHERE po.state = 'purchase'
                   AND po.company_id = %(company_id)s
                   AND po.date_approve IS NOT NULL
                   AND po.date_approve <= %(end)s
                   AND pol.display_type IS NULL
                   AND pol.product_id = ANY(%(product_ids)s)
                   AND COALESCE(pol.is_downpayment, FALSE) = FALSE
                WINDOW w_asc AS (PARTITION BY pol.product_id ORDER BY po.date_approve, pol.id),
                       w_desc AS (PARTITION BY pol.product_id ORDER BY po.date_approve DESC, pol.id DESC)
            )
            SELECT id, product_id, prev_id, rn
              FROM hist
             WHERE %(outer)s
             ORDER BY product_id, rn
            """,
            company_id=company.id,
            end=end,
            product_ids=list(product_ids),
            outer=outer_condition,
        ))
        return self.env.cr.fetchall()

    def _browse_lines(self, fetched):
        ids = {line_id for line_id, _p, _prev, _rn in fetched}
        ids |= {prev_id for _l, _p, prev_id, _rn in fetched if prev_id}
        lines = self.env['purchase.order.line'].sudo().browse(ids)
        return {line.id: line for line in lines}

    def _unit_price(self, line):
        """Discounted price of one product base unit, in company currency."""
        price = line.price_unit * (1.0 - (line.discount or 0.0) / 100.0)
        line_uom = line.product_uom_id if 'product_uom_id' in line._fields else line.uom_id
        if line_uom and line.product_id.uom_id:
            price = line_uom._compute_price(price, line.product_id.uom_id)
        return price / (line.order_id.currency_rate or 1.0)

    def _build_row(self, line, prev_line, currency):
        product = line.product_id
        last_price = self._unit_price(line)
        prev_price = self._unit_price(prev_line) if prev_line else None

        trend, diff, pct = 'new', 0.0, None
        if prev_line:
            comparison = currency.compare_amounts(last_price, prev_price)
            trend = 'up' if comparison > 0 else 'down' if comparison < 0 else 'same'
            diff = last_price - prev_price if trend != 'same' else 0.0
            pct = (diff / prev_price * 100.0) if prev_price else None

        return {
            'product_id': product.id,
            'product_name': product.name,
            'default_code': product.default_code or '',
            'uom': product.uom_id.name or '',
            'last_price': last_price,
            'last_qty': line.product_uom_qty,
            'last_vendor': line.order_id.partner_id.display_name,
            'last_order_id': line.order_id.id,
            'last_order_name': line.order_id.name,
            'last_date': self._local_date_str(line.order_id.date_approve),
            'prev_price': prev_price,
            'prev_vendor': prev_line.order_id.partner_id.display_name if prev_line else '',
            'prev_order_id': prev_line.order_id.id if prev_line else False,
            'prev_order_name': prev_line.order_id.name if prev_line else '',
            'prev_date': self._local_date_str(prev_line.order_id.date_approve) if prev_line else '',
            'diff': diff,
            'pct': pct,
            'trend': trend,
            'impact': 0.0,
        }

    @staticmethod
    def _sort_rows(rows):
        return sorted(rows, key=lambda r: (TREND_ORDER[r['trend']], -abs(r['pct'] or 0.0), -abs(r['diff'])))

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    def _check_dashboard_access(self):
        if not self.env.user.has_group('ceo_main_dashboard.group_ceo_main_dashboard_user'):
            raise AccessError(_("You are not allowed to access the CEO Main Dashboard."))

    def _parse_range(self, date_from, date_to):
        today = fields.Date.context_today(self)
        date_from = fields.Date.to_date(date_from) or today
        date_to = fields.Date.to_date(date_to) or today
        if date_from > date_to:
            date_from, date_to = date_to, date_from
        return date_from, date_to

    def _user_tz(self):
        try:
            return pytz.timezone(self.env.context.get('tz') or self.env.user.tz or 'UTC')
        except pytz.UnknownTimeZoneError:
            return pytz.utc

    def _utc_bounds(self, date_from, date_to):
        """Naive UTC datetimes covering the local days [date_from, date_to]."""
        tz = self._user_tz()
        start = tz.localize(datetime.combine(date_from, time.min)).astimezone(pytz.utc)
        end = tz.localize(datetime.combine(date_to, time.max)).astimezone(pytz.utc)
        return start.replace(tzinfo=None), end.replace(tzinfo=None)

    def _local_date_str(self, dt):
        if not dt:
            return ''
        return fields.Date.to_string(pytz.utc.localize(dt).astimezone(self._user_tz()).date())

    def _period_line_domain(self, company, start, end):
        return [
            ('order_id.state', '=', 'purchase'),
            ('order_id.company_id', '=', company.id),
            ('order_id.date_approve', '>=', start),
            ('order_id.date_approve', '<=', end),
            ('display_type', '=', False),
            ('product_id', '!=', False),
            ('is_downpayment', '=', False),
        ]

    def _confirmed_orders(self, company, date_from, date_to):
        start, end = self._utc_bounds(date_from, date_to)
        return self.env['purchase.order'].sudo().search([
            ('company_id', '=', company.id),
            ('state', '=', 'purchase'),
            ('date_approve', '>=', start),
            ('date_approve', '<=', end),
        ], order='date_approve desc, id desc')

    @staticmethod
    def _pct_change(new, old):
        if not old:
            return None
        return (new - old) / abs(old) * 100.0
