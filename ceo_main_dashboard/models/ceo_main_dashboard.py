# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import SQL

TREND_ORDER = {'up': 0, 'down': 0, 'same': 1, 'new': 2}
BILLING_FILTERS = ('all', 'invoiced', 'not_invoiced')
RATIO_EPSILON = 1e-4


class CeoMainDashboard(models.AbstractModel):
    """Data engine of the CEO Main Dashboard.

    Everything is based on what was actually received in the warehouse:
    a purchase order line counts as a purchase once it has a validated receipt,
    purchases are ordered by their first receipt date, and quantities / values
    use the received quantity (returns to the vendor are deducted).

    Unit prices come from the purchase order line, normalized to the product's
    base unit of measure, discount included, and converted to the company
    currency with the rate stored on the order.

    Billing filter: the billed share of a line is its quantity on posted vendor
    bills (minus posted refunds) divided by its received quantity. With the
    'invoiced' filter only that share of the line's received quantities and
    values is counted, with 'not_invoiced' only the remaining share.
    """
    _name = 'ceo.main.dashboard'
    _description = 'CEO Main Dashboard'

    _SEARCH_PRODUCT_LIMIT = 200
    _HISTORY_LIMIT = 12
    _RECENT_RECEIPTS_LIMIT = 10

    # ---------------------------------------------------------------------
    # Public entry points (called from the OWL client action)
    # ---------------------------------------------------------------------
    @api.model
    def get_purchase_dashboard(self, date_from=None, date_to=None, billing='all'):
        self._check_dashboard_access()
        self._check_billing(billing)
        date_from, date_to = self._parse_range(date_from, date_to)
        company = self.env.company
        currency = company.currency_id
        start, end = self._utc_bounds(date_from, date_to)

        moves, ratios = self._received_moves(company, date_from, date_to, billing)
        compared_moves = moves if billing == 'all' else self._received_moves(company, date_from, date_to)[0]
        rows, impact = self._get_period_price_comparison(company, compared_moves, end)

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
            'billing': billing,
            'summary': self._get_purchase_summary(company, moves, ratios, billing, date_from, date_to),
            'impact': impact,
            'price_rows': rows,
            'daily': self._get_daily_totals(moves, ratios, billing, date_from, date_to),
            'recent_receipts': self._get_recent_receipts(moves, ratios, billing),
        }

    @api.model
    def search_purchase_prices(self, term, date_to=None):
        """Latest vs previous billed price of matching products, whole history up to date_to."""
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
        ratios = self._billing_ratios(self._lines_recordset(lines))
        bills = self._bill_unit_prices(self._lines_recordset(lines))
        rows = [self._build_row(rec, lines, ratios, bills, company.currency_id) for rec in fetched]
        return self._sort_rows(rows)

    @api.model
    def get_product_price_history(self, product_id, date_to=None):
        """Last billed purchases of one product, oldest first, with the change vs the one billed before."""
        self._check_dashboard_access()
        company = self.env.company
        _dummy, date_to = self._parse_range(date_to, date_to)
        _start, end = self._utc_bounds(date_to, date_to)
        fetched = self._fetch_price_lines(company, end, [product_id], SQL("hist.rn <= %s", self._HISTORY_LIMIT))
        lines = self._browse_lines(fetched)
        ratios = self._billing_ratios(self._lines_recordset(lines))
        bills_by_line = self._bill_unit_prices(self._lines_recordset(lines))
        currency = company.currency_id

        history = []
        for rec in reversed(fetched):
            line = lines[rec['id']]
            row = self._build_row(rec, lines, ratios, bills_by_line, currency)
            po_price = self._unit_price(line)
            bills = bills_by_line.get(line.id, [])
            for bill in bills:
                diff = bill['price'] - po_price
                bill['diff'] = 0.0 if currency.is_zero(diff) else diff
                bill['pct'] = (bill['diff'] / po_price * 100.0) if po_price else None
            history.append({
                'line_id': line.id,
                'order_id': line.order_id.id,
                'order_name': line.order_id.name,
                'vendor': line.order_id.partner_id.display_name,
                'date': row['last_date'],
                'qty': row['last_qty'],
                'ordered_qty': row['last_ordered_qty'],
                'billed_qty': row['billed_qty'],
                'billing_status': row['billing_status'],
                'uom': row['uom'],
                'price': row['last_price'],
                'po_price': po_price,
                'multi_price': row['multi_price'],
                'bills': bills,
                'diff': row['diff'],
                'pct': row['pct'],
                'trend': row['trend'],
            })
        return history

    @api.model
    def action_open_period_bills(self, date_from=None, date_to=None):
        """Posted vendor bills and refunds of purchase orders, by accounting date in the period."""
        self._check_dashboard_access()
        date_from, date_to = self._parse_range(date_from, date_to)
        return {
            'type': 'ir.actions.act_window',
            'name': _("Vendor Bills"),
            'res_model': 'account.move',
            'views': [
                (self.env.ref('account.view_in_invoice_bill_tree').id, 'list'),
                (self.env.ref('account.view_move_form').id, 'form'),
            ],
            'search_view_id': [self.env.ref('account.view_account_invoice_filter').id],
            'domain': [
                ('company_id', '=', self.env.company.id),
                ('move_type', 'in', ('in_invoice', 'in_refund')),
                ('state', '=', 'posted'),
                ('date', '>=', fields.Date.to_string(date_from)),
                ('date', '<=', fields.Date.to_string(date_to)),
                ('line_ids.purchase_line_id', '!=', False),
            ],
            'context': {'default_move_type': 'in_invoice', 'create': False},
            'target': 'current',
        }

    # ---------------------------------------------------------------------
    # Summary, daily totals and recent receipts
    # ---------------------------------------------------------------------
    def _get_purchase_summary(self, company, moves, ratios, billing, date_from, date_to):
        today = fields.Date.context_today(self)
        yesterday = today - timedelta(days=1)
        span = date_to - date_from
        prev_to = date_from - timedelta(days=1)
        prev_from = prev_to - span

        period_total = self._received_value(moves, ratios, billing)
        prev_total = self._received_value(*self._received_moves(company, prev_from, prev_to, billing), billing)
        today_moves, today_ratios = self._received_moves(company, today, today, billing)
        today_total = self._received_value(today_moves, today_ratios, billing)
        yesterday_total = self._received_value(*self._received_moves(company, yesterday, yesterday, billing), billing)
        receipt_count = self._receipt_count(moves)

        return {
            'period_total': period_total,
            'period_count': receipt_count,
            'prev_period_total': prev_total,
            'prev_period_from': fields.Date.to_string(prev_from),
            'prev_period_to': fields.Date.to_string(prev_to),
            'period_change_pct': self._pct_change(period_total, prev_total),
            'vendor_count': len(moves.purchase_line_id.order_id.partner_id),
            'avg_receipt': period_total / receipt_count if receipt_count else 0.0,
            'today_total': today_total,
            'today_count': self._receipt_count(today_moves),
            'yesterday_total': yesterday_total,
            'today_change_pct': self._pct_change(today_total, yesterday_total),
        }

    def _get_daily_totals(self, moves, ratios, billing, date_from, date_to):
        by_month = (date_to - date_from).days > 62
        tz = self._user_tz()
        buckets = defaultdict(lambda: {'amount': 0.0, 'pickings': set()})
        for move in moves:
            local_date = pytz.utc.localize(move.date).astimezone(tz).date()
            key = local_date.replace(day=1) if by_month else local_date
            buckets[key]['amount'] += self._move_value(move, ratios, billing)
            if move.picking_id:
                buckets[key]['pickings'].add(move.picking_id.id)

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
                'count': len(buckets[key]['pickings']),
            } for key in keys],
        }

    def _get_recent_receipts(self, moves, ratios, billing):
        tz = self._user_tz()
        by_picking = defaultdict(lambda: self.env['stock.move'].sudo())
        for move in moves.filtered('picking_id'):
            by_picking[move.picking_id] |= move

        receipts = []
        for picking, picking_moves in by_picking.items():
            done_date = max(picking_moves.mapped('date'))
            orders = picking_moves.purchase_line_id.order_id
            statuses = {self._billing_status(ratios.get(line.id, 0.0)) for line in picking_moves.purchase_line_id}
            receipts.append({
                'id': picking.id,
                'name': picking.name,
                'vendor': (picking.partner_id or orders[:1].partner_id).display_name or '',
                'orders': ', '.join(orders.mapped('name')),
                'amount': self._received_value(picking_moves, ratios, billing),
                'date': fields.Datetime.to_string(pytz.utc.localize(done_date).astimezone(tz).replace(tzinfo=None)),
                'is_return': any(m._is_purchase_return() for m in picking_moves),
                'billing_status': statuses.pop() if len(statuses) == 1 else 'partial',
                'line_count': len(picking_moves),
                '_sort': done_date,
            })
        receipts.sort(key=lambda r: r.pop('_sort'), reverse=True)
        return receipts[:self._RECENT_RECEIPTS_LIMIT]

    # ---------------------------------------------------------------------
    # Price comparison
    # ---------------------------------------------------------------------
    def _get_period_price_comparison(self, company, moves, end):
        """One row per product with a billed purchase line received in the period (the latest one
        vs the billed line received before it), plus the money impact of every receipt in the
        period. Prices are the highest bill price of each line; lines without a posted bill are ignored."""
        currency = company.currency_id
        impact = {
            'extra_paid': 0.0, 'saved': 0.0, 'net': 0.0,
            'up_count': 0, 'down_count': 0, 'same_count': 0, 'new_count': 0, 'product_count': 0,
        }
        if not moves:
            return [], impact

        fetched = self._fetch_price_lines(
            company, end, moves.product_id.ids, SQL("hist.id = ANY(%s)", moves.purchase_line_id.ids))
        lines = self._browse_lines(fetched)
        ratios = self._billing_ratios(self._lines_recordset(lines))
        bills = self._bill_unit_prices(self._lines_recordset(lines))
        prev_of = {rec['id']: rec['prev_id'] for rec in fetched}

        # Receipts and returns of the same line are netted before splitting into extra paid / saved.
        line_impact = defaultdict(float)
        for move in moves:
            line = move.purchase_line_id
            prev_id = prev_of.get(line.id)
            if not prev_id:
                continue
            diff = self._compare_price(line, bills) - self._compare_price(lines[prev_id], bills)
            if not currency.is_zero(diff):
                line_impact[line] += diff * self._move_received_qty(move)

        product_impact = defaultdict(float)
        for line, amount in line_impact.items():
            product_impact[line.product_id.id] += amount
            if amount > 0:
                impact['extra_paid'] += amount
            else:
                impact['saved'] -= amount

        latest = {}
        for rec in fetched:
            current = latest.get(rec['product_id'])
            if current is None or rec['rn'] < current['rn']:
                latest[rec['product_id']] = rec

        rows = []
        for product_id, rec in latest.items():
            row = self._build_row(rec, lines, ratios, bills, currency)
            row['impact'] = product_impact.get(product_id, 0.0)
            impact[f"{row['trend']}_count"] += 1
            rows.append(row)

        impact['net'] = impact['extra_paid'] - impact['saved']
        impact['product_count'] = len(rows)
        return self._sort_rows(rows), impact

    def _fetch_price_lines(self, company, end, product_ids, outer_condition):
        """Received and billed purchase lines of the given products, ranked per product by first receipt date.

        Returns dicts with: id, product_id, first_date, prev_id / prev_date (billed line received
        right before, any vendor) and rn (1 = most recently received billed line of the product).
        Only lines with a validated receipt up to `end`, a positive received quantity and a
        posted vendor bill count.
        """
        if not product_ids:
            return []
        self.env['purchase.order'].flush_model(['state', 'company_id'])
        self.env['purchase.order.line'].flush_model(
            ['order_id', 'product_id', 'display_type', 'is_downpayment', 'qty_received'])
        self.env['stock.move'].flush_model(
            ['state', 'date', 'purchase_line_id', 'product_id', 'location_dest_id', 'origin_returned_move_id'])
        self.env['account.move'].flush_model(['state', 'move_type'])
        self.env['account.move.line'].flush_model(['move_id', 'purchase_line_id', 'quantity'])
        self.env.cr.execute(SQL(
            """
            WITH receipts AS (
                SELECT sm.purchase_line_id AS line_id,
                       MIN(sm.date) AS first_date
                  FROM stock_move sm
                  JOIN stock_location dest ON dest.id = sm.location_dest_id
                  JOIN purchase_order_line pol ON pol.id = sm.purchase_line_id
                 WHERE sm.state = 'done'
                   AND sm.date <= %(end)s
                   AND sm.product_id = pol.product_id
                   AND sm.origin_returned_move_id IS NULL
                   AND dest.usage != 'supplier'
                   AND pol.product_id = ANY(%(product_ids)s)
                 GROUP BY sm.purchase_line_id
            ),
            hist AS (
                SELECT pol.id,
                       pol.product_id,
                       r.first_date,
                       LAG(pol.id) OVER w_asc AS prev_id,
                       LAG(r.first_date) OVER w_asc AS prev_date,
                       ROW_NUMBER() OVER w_desc AS rn
                  FROM receipts r
                  JOIN purchase_order_line pol ON pol.id = r.line_id
                  JOIN purchase_order po ON po.id = pol.order_id
                 WHERE po.state = 'purchase'
                   AND po.company_id = %(company_id)s
                   AND pol.display_type IS NULL
                   AND COALESCE(pol.is_downpayment, FALSE) = FALSE
                   AND pol.qty_received > 0
                   AND EXISTS (
                       SELECT 1
                         FROM account_move_line aml
                         JOIN account_move am ON am.id = aml.move_id
                        WHERE aml.purchase_line_id = pol.id
                          AND am.state = 'posted'
                          AND am.move_type = 'in_invoice'
                          AND aml.quantity > 0
                   )
                WINDOW w_asc AS (PARTITION BY pol.product_id ORDER BY r.first_date, pol.id),
                       w_desc AS (PARTITION BY pol.product_id ORDER BY r.first_date DESC, pol.id DESC)
            )
            SELECT id, product_id, first_date, prev_id, prev_date, rn
              FROM hist
             WHERE %(outer)s
             ORDER BY product_id, rn
            """,
            company_id=company.id,
            end=end,
            product_ids=list(product_ids),
            outer=outer_condition,
        ))
        return self.env.cr.dictfetchall()

    def _browse_lines(self, fetched):
        ids = {rec['id'] for rec in fetched} | {rec['prev_id'] for rec in fetched if rec['prev_id']}
        lines = self.env['purchase.order.line'].sudo().browse(ids)
        return {line.id: line for line in lines}

    def _lines_recordset(self, lines_by_id):
        return self.env['purchase.order.line'].sudo().browse(list(lines_by_id))

    def _build_row(self, rec, lines, ratios, bills, currency):
        line = lines[rec['id']]
        prev_line = lines[rec['prev_id']] if rec['prev_id'] else None
        product = line.product_id
        last_price = self._compare_price(line, bills)
        prev_price = self._compare_price(prev_line, bills) if prev_line else None
        received_qty = self._line_qty_in_product_uom(line, line.qty_received)
        ratio = ratios.get(line.id, 0.0)

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
            'last_po_price': self._unit_price(line),
            'multi_price': self._has_multi_bill_price(line, bills, currency),
            'prev_multi_price': self._has_multi_bill_price(prev_line, bills, currency) if prev_line else False,
            'last_qty': received_qty,
            'last_ordered_qty': line.product_uom_qty,
            'billed_qty': received_qty * ratio,
            'billing_status': self._billing_status(ratio),
            'last_vendor': line.order_id.partner_id.display_name,
            'last_order_id': line.order_id.id,
            'last_order_name': line.order_id.name,
            'last_date': self._local_date_str(rec['first_date']),
            'prev_price': prev_price,
            'prev_vendor': prev_line.order_id.partner_id.display_name if prev_line else '',
            'prev_order_id': prev_line.order_id.id if prev_line else False,
            'prev_order_name': prev_line.order_id.name if prev_line else '',
            'prev_date': self._local_date_str(rec['prev_date']) if prev_line else '',
            'diff': diff,
            'pct': pct,
            'trend': trend,
            'impact': 0.0,
        }

    @staticmethod
    def _sort_rows(rows):
        return sorted(rows, key=lambda r: (TREND_ORDER[r['trend']], -abs(r['pct'] or 0.0), -abs(r['diff'])))

    # ---------------------------------------------------------------------
    # Billing (posted vendor bills)
    # ---------------------------------------------------------------------
    def _billing_ratios(self, lines):
        """Share (0..1) of each line's received quantity that is on posted vendor bills."""
        lines = lines.filtered(lambda l: l.qty_received > 0)
        if not lines:
            return {}
        AccountMoveLine = self.env['account.move.line'].sudo()
        billed = defaultdict(float)
        for move_type, sign in (('in_invoice', 1.0), ('in_refund', -1.0)):
            groups = AccountMoveLine._read_group(
                [
                    ('purchase_line_id', 'in', lines.ids),
                    ('parent_state', '=', 'posted'),
                    ('move_id.move_type', '=', move_type),
                ],
                ['purchase_line_id', 'product_uom_id'],
                ['quantity:sum'],
            )
            for line, uom, quantity in groups:
                to_uom = line.product_id.uom_id
                if uom and to_uom:
                    quantity = uom._compute_quantity(quantity, to_uom, rounding_method='HALF-UP')
                billed[line.id] += sign * quantity

        ratios = {}
        for line in lines:
            received = self._line_qty_in_product_uom(line, line.qty_received)
            ratios[line.id] = min(max(billed[line.id] / received, 0.0), 1.0) if received > 0 else 0.0
        return ratios

    def _bill_unit_prices(self, lines):
        """Per line, one entry per posted vendor bill / refund with its untaxed unit price (discount
        included, per product base unit, in company currency), ordered by bill date."""
        if not lines:
            return {}
        groups = self.env['account.move.line'].sudo()._read_group(
            [
                ('purchase_line_id', 'in', lines.ids),
                ('parent_state', '=', 'posted'),
                ('move_id.move_type', 'in', ('in_invoice', 'in_refund')),
            ],
            ['purchase_line_id', 'move_id', 'product_uom_id'],
            ['quantity:sum', 'balance:sum'],
        )
        totals = defaultdict(lambda: [0.0, 0.0])
        for line, move, uom, quantity, balance in groups:
            to_uom = line.product_id.uom_id
            if uom and to_uom:
                quantity = uom._compute_quantity(quantity, to_uom, rounding_method='HALF-UP')
            totals[line, move][0] += quantity
            totals[line, move][1] += balance

        bills = defaultdict(list)
        for (line, move), (quantity, balance) in sorted(
                totals.items(), key=lambda item: (item[0][1].date, item[0][1].id)):
            if quantity <= 0:
                continue
            bills[line.id].append({
                'id': move.id,
                'name': move.name,
                'date': fields.Date.to_string(move.date),
                'is_refund': move.move_type == 'in_refund',
                'qty': quantity,
                'price': abs(balance) / quantity,
            })
        return bills

    @staticmethod
    def _invoice_prices(line, bills):
        return [bill['price'] for bill in bills.get(line.id, []) if not bill['is_refund']]

    def _compare_price(self, line, bills):
        """Highest unit price of the line on its posted vendor bills (PO price if it has none)."""
        prices = self._invoice_prices(line, bills)
        return max(prices) if prices else self._unit_price(line)

    def _has_multi_bill_price(self, line, bills, currency):
        prices = self._invoice_prices(line, bills)
        return len(prices) > 1 and not currency.is_zero(max(prices) - min(prices))

    @staticmethod
    def _billing_factor(ratio, billing):
        if billing == 'invoiced':
            return ratio
        if billing == 'not_invoiced':
            return 1.0 - ratio
        return 1.0

    @staticmethod
    def _billing_status(ratio):
        if ratio >= 1.0 - RATIO_EPSILON:
            return 'invoiced'
        if ratio <= RATIO_EPSILON:
            return 'none'
        return 'partial'

    def _check_billing(self, billing):
        if billing not in BILLING_FILTERS:
            raise UserError(_("Invalid billing filter: %s", billing))

    # ---------------------------------------------------------------------
    # Receipts, quantities and prices
    # ---------------------------------------------------------------------
    def _received_moves(self, company, date_from, date_to, billing='all'):
        """Validated stock moves of purchase lines (receipts and vendor returns) in the local days range,
        restricted to lines matching the billing filter. Returns (moves, billing ratios by line id)."""
        start, end = self._utc_bounds(date_from, date_to)
        moves = self.env['stock.move'].sudo().search([
            ('company_id', '=', company.id),
            ('state', '=', 'done'),
            ('purchase_line_id', '!=', False),
            ('purchase_line_id.order_id.state', '=', 'purchase'),
            ('purchase_line_id.display_type', '=', False),
            ('date', '>=', start),
            ('date', '<=', end),
        ], order='date desc, id desc')
        moves = moves.filtered(lambda m: m.product_id == m.purchase_line_id.product_id)
        ratios = self._billing_ratios(moves.purchase_line_id)
        if billing != 'all':
            moves = moves.filtered(
                lambda m: self._billing_factor(ratios.get(m.purchase_line_id.id, 0.0), billing) > RATIO_EPSILON)
        return moves, ratios

    def _move_received_qty(self, move):
        """Signed received quantity of a done move in the product's base unit.

        Mirrors purchase_stock's received quantity rules: receipts add, returns to the vendor
        deduct, re-receipts of returns that did not update the PO are ignored.
        """
        move_uom = move.product_uom if 'product_uom' in move._fields else move.uom_id
        qty = move_uom._compute_quantity(move.quantity, move.product_id.uom_id, rounding_method='HALF-UP')
        origin = move.origin_returned_move_id
        if move._is_purchase_return():
            return -qty if (not origin or move.to_refund) else 0.0
        if origin and origin._is_dropshipped() and not move._is_dropshipped_returned():
            return 0.0
        if origin and origin._is_purchase_return() and not move.to_refund:
            return 0.0
        return qty

    def _receipt_count(self, moves):
        """Number of receipt documents, vendor returns excluded."""
        return len(moves.filtered(lambda m: not m._is_purchase_return()).picking_id)

    def _move_value(self, move, ratios, billing):
        line = move.purchase_line_id
        factor = self._billing_factor(ratios.get(line.id, 0.0), billing)
        return self._move_received_qty(move) * self._unit_price(line) * factor

    def _received_value(self, moves, ratios, billing):
        return sum(self._move_value(move, ratios, billing) for move in moves)

    def _line_uom(self, line):
        return line.product_uom_id if 'product_uom_id' in line._fields else line.uom_id

    def _line_qty_in_product_uom(self, line, qty):
        line_uom = self._line_uom(line)
        if line_uom and line.product_id.uom_id:
            return line_uom._compute_quantity(qty, line.product_id.uom_id, rounding_method='HALF-UP')
        return qty

    def _unit_price(self, line):
        """Discounted price of one product base unit, in company currency."""
        price = line.price_unit * (1.0 - (line.discount or 0.0) / 100.0)
        line_uom = self._line_uom(line)
        if line_uom and line.product_id.uom_id:
            price = line_uom._compute_price(price, line.product_id.uom_id)
        return price / (line.order_id.currency_rate or 1.0)

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

    @staticmethod
    def _pct_change(new, old):
        if not old:
            return None
        return (new - old) / abs(old) * 100.0
