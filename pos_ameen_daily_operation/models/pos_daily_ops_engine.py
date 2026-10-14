from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models

# Pledges, advance orders and attendance are dated with a business day that starts at
# 06:00 local time and ends at 06:00 the next morning, so after-midnight activity stays
# on the day the shift started.
BUSINESS_DAY_START = time(6, 0)

DELIVERY_CHANNELS = ('talabat', 'careem', 'mythings', 'kabseh')

FIGURE_KEYS = (
    'sales', 'cash', 'visa', 'hospitality', 'employee_debt', 'other_sales',
    'talabat', 'careem', 'mythings', 'kabseh', 'online_sales',
    'cash_in', 'cash_out', 'delivery_amount', 'delivery_cash',
    'rahen_in', 'rahen_out', 'pledge_cash_in', 'pledge_cash_out',
    'pledge_visa_in', 'pledge_visa_out', 'differences',
)


class PosDailyOpsEngine(models.AbstractModel):
    _name = 'pos.daily.ops.engine'
    _description = 'Daily Operations Figures Engine'

    # ------------------------------------------------------------------
    # Period
    # ------------------------------------------------------------------

    @api.model
    def _get_timezone(self):
        tz_name = (
            self.env.context.get('tz')
            or self.env.user.tz
            or self.env.company.resource_calendar_id.tz
            or 'UTC'
        )
        return pytz.timezone(tz_name)

    @api.model
    def _to_utc(self, local_dt):
        return self._get_timezone().localize(local_dt).astimezone(pytz.UTC).replace(tzinfo=None)

    @api.model
    def _to_local_date(self, utc_dt):
        return pytz.UTC.localize(utc_dt).astimezone(self._get_timezone()).date()

    @api.model
    def _get_period(self, date_from, date_to=None):
        """Return the UTC-naive bounds used for a range of business dates.

        Sessions belong to the date they were opened on (local calendar day).
        Pledge, advance order and attendance events use the business-day window
        [date_from 06:00, date_to + 1 day 06:00).
        """
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to) if date_to else date_from
        if date_to < date_from:
            date_from, date_to = date_to, date_from
        return {
            'date_from': date_from,
            'date_to': date_to,
            'session_start': self._to_utc(datetime.combine(date_from, time.min)),
            'session_end': self._to_utc(datetime.combine(date_to, time.max)),
            'business_start': self._to_utc(datetime.combine(date_from, BUSINESS_DAY_START)),
            'business_end': self._to_utc(datetime.combine(date_to + timedelta(days=1), BUSINESS_DAY_START)),
        }

    @api.model
    def _in_business_window(self, period, dt):
        return bool(dt) and period['business_start'] <= dt < period['business_end']

    # ------------------------------------------------------------------
    # Source records
    # ------------------------------------------------------------------

    @api.model
    def _get_sessions(self, period, configs):
        if not configs:
            return self.env['pos.session']
        return self.env['pos.session'].sudo().search([
            ('start_at', '>=', period['session_start']),
            ('start_at', '<=', period['session_end']),
            ('config_id', 'in', configs.ids),
        ], order='start_at asc')

    @api.model
    def _get_payments(self, sessions):
        if not sessions:
            return self.env['pos.payment']
        return self.env['pos.payment'].sudo().search([('session_id', 'in', sessions.ids)])

    @api.model
    def _get_orders(self, sessions):
        if not sessions:
            return self.env['pos.order']
        return self.env['pos.order'].sudo().search([
            ('session_id', 'in', sessions.ids),
            ('state', 'in', ('paid', 'done', 'invoiced')),
        ])

    @api.model
    def _get_cash_move_lines(self, sessions):
        return sessions.sudo().statement_line_ids

    # ------------------------------------------------------------------
    # Payment method mapping
    # ------------------------------------------------------------------

    @api.model
    def _get_bucket(self, payment_method):
        return payment_method.daily_ops_report_type or 'none'

    @api.model
    def _is_in_sales(self, payment_method):
        return self._get_bucket(payment_method) != 'hospitality'

    @api.model
    def _get_channel(self, payment_method):
        """'cash', 'visa' or False, used to split pledge and advance deposits."""
        bucket = self._get_bucket(payment_method) if payment_method else 'none'
        return bucket if bucket in ('cash', 'visa') else False

    # ------------------------------------------------------------------
    # Pledges (Rahen)
    # ------------------------------------------------------------------

    @api.model
    def _split_by_payments(self, payments):
        cash = visa = 0.0
        for payment in payments:
            channel = self._get_channel(payment.payment_method_id)
            if channel == 'cash':
                cash += payment.amount or 0.0
            elif channel == 'visa':
                visa += payment.amount or 0.0
        cash, visa = abs(cash), abs(visa)
        total = cash + visa
        if not total:
            return None
        return cash / total, visa / total

    @api.model
    def _pledge_receive_split(self, pledge):
        split = None
        if pledge.pos_order_id:
            split = self._split_by_payments(pledge.pos_order_id.payment_ids)
        return split or (1.0, 0.0)

    @api.model
    def _pledge_return_split(self, pledge):
        split = None
        channel = self._get_channel(pledge.return_payment_method_id)
        if channel:
            split = (1.0, 0.0) if channel == 'cash' else (0.0, 1.0)
        elif pledge.return_pos_order_id:
            split = self._split_by_payments(pledge.return_pos_order_id.payment_ids)
        return split or self._pledge_receive_split(pledge)

    @api.model
    def _pledge_amount(self, pledge):
        return pledge.pledge_subtotal or (pledge.pledge_qty or 0.0) * (pledge.pledge_amount_unit or 0.0)

    @api.model
    def _pledge_receive_branch(self, pledge):
        if pledge.pos_order_id:
            return pledge.pos_order_id.config_id
        return pledge.order_id.pos_config_id or pledge.order_id.from_pos_config_id

    @api.model
    def _pledge_return_branch(self, pledge):
        return (
            pledge.return_pos_session_id.config_id
            or pledge.return_pos_order_id.config_id
            or self._pledge_receive_branch(pledge)
        )

    @api.model
    def _get_pledge_movements(self, period, configs):
        """Pledge cash-drawer movements in the business-day window.

        Rahen In: Active/Returned pledges received in the window, at the receiving branch.
        Rahen Out: pledges returned in the window (whenever received), at the returning branch.
        """
        start, end = period['business_start'], period['business_end']
        config_ids = set(configs.ids)
        pledges = self.env['pos.advance.order.pledge'].sudo().search([
            '|', '|', '|',
            '&', ('receive_date', '>=', start), ('receive_date', '<', end),
            '&', ('create_date', '>=', start), ('create_date', '<', end),
            '&', ('return_date', '>=', start), ('return_date', '<', end),
            '&', '&', ('state', '=', 'returned'), ('return_date', '=', False),
            '&', ('write_date', '>=', start), ('write_date', '<', end),
        ], order='id desc')

        movements = []
        for pledge in pledges:
            amount = self._pledge_amount(pledge)
            if not amount:
                continue

            received_at = pledge.receive_date or pledge.create_date
            if pledge.state in ('active', 'returned') and self._in_business_window(period, received_at):
                config = self._pledge_receive_branch(pledge)
                if config and config.id in config_ids:
                    cash_ratio, visa_ratio = self._pledge_receive_split(pledge)
                    movements.append({
                        'pledge': pledge,
                        'type': 'in',
                        'date': received_at,
                        'config': config,
                        'amount': amount,
                        'cash': amount * cash_ratio,
                        'visa': amount * visa_ratio,
                        'pos_order': pledge.pos_order_id,
                        'payment_method': self.env['pos.payment.method'],
                    })

            returned_at = pledge.return_date or pledge.write_date
            if pledge.state == 'returned' and self._in_business_window(period, returned_at):
                config = self._pledge_return_branch(pledge)
                if config and config.id in config_ids:
                    cash_ratio, visa_ratio = self._pledge_return_split(pledge)
                    movements.append({
                        'pledge': pledge,
                        'type': 'out',
                        'date': returned_at,
                        'config': config,
                        'amount': amount,
                        'cash': amount * cash_ratio,
                        'visa': amount * visa_ratio,
                        'pos_order': pledge.return_pos_order_id or pledge.pos_order_id,
                        'payment_method': pledge.return_payment_method_id,
                    })
        return movements

    # ------------------------------------------------------------------
    # Branch figures
    # ------------------------------------------------------------------

    @api.model
    def _empty_figures(self):
        return dict.fromkeys(FIGURE_KEYS, 0.0)

    @api.model
    def _add_payment_figures(self, figures, sessions):
        if not sessions:
            return
        groups = self.env['pos.payment'].sudo()._read_group(
            [('session_id', 'in', sessions.ids)],
            ['session_id', 'payment_method_id'],
            ['amount:sum'],
        )
        for session, payment_method, amount in groups:
            values = figures.get(session.config_id.id)
            if values is None:
                continue
            amount = amount or 0.0
            bucket = self._get_bucket(payment_method)
            if bucket != 'hospitality':
                values['sales'] += amount
            values['other_sales' if bucket == 'none' else bucket] += amount

    @api.model
    def _add_session_figures(self, figures, sessions):
        for session in sessions.sudo():
            values = figures.get(session.config_id.id)
            if values is None:
                continue
            values['delivery_amount'] += session.delivery_amount or 0.0
            for line in session.statement_line_ids:
                amount = line.amount or 0.0
                if amount > 0:
                    values['cash_in'] += amount
                else:
                    values['cash_out'] += abs(amount)

    @api.model
    def _add_pledge_figures(self, figures, movements):
        for move in movements:
            values = figures.get(move['config'].id)
            if values is None:
                continue
            side = move['type']
            values['rahen_%s' % side] += move['amount']
            values['pledge_cash_%s' % side] += move['cash']
            values['pledge_visa_%s' % side] += move['visa']

    @api.model
    def _compute_branch_figures(self, period, configs, sessions=None, pledge_movements=None):
        """Return {config_id: figures} shared by the Excel report and the dashboard."""
        if sessions is None:
            sessions = self._get_sessions(period, configs)
        if pledge_movements is None:
            pledge_movements = self._get_pledge_movements(period, configs)

        figures = {config.id: self._empty_figures() for config in configs}
        self._add_payment_figures(figures, sessions)
        self._add_session_figures(figures, sessions)
        self._add_pledge_figures(figures, pledge_movements)

        for values in figures.values():
            values['online_sales'] = sum(values[channel] for channel in DELIVERY_CHANNELS)
            values['delivery_cash'] = values['cash_out'] + values['delivery_amount']
            values['differences'] = values['cash'] + values['rahen_in'] - values['delivery_cash']
        return figures
