from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class AnabtawiDirectOrder(models.Model):
    _name = 'anabtawi.direct.order'
    _description = 'Direct / Aggregator Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(default='New', copy=False, readonly=True)
    channel = fields.Selection([
        ('direct_app', 'Direct App'),
        ('website', 'Website'),
        ('qr', 'QR Menu'),
        ('talabat', 'Talabat'),
        ('careem', 'Careem'),
        ('manual', 'Manual'),
    ], default='direct_app', required=True, tracking=True)
    external_order_ref = fields.Char(index=True, copy=False)
    branch_id = fields.Many2one('anabtawi.ordering.branch', required=True, tracking=True)
    company_id = fields.Many2one('res.company', related='branch_id.company_id', store=True, readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer')
    customer_name = fields.Char(required=True)
    customer_phone = fields.Char(required=True)
    customer_address = fields.Text()
    zone_id = fields.Many2one('anabtawi.delivery.zone')
    order_type = fields.Selection([('delivery', 'Delivery'), ('pickup', 'Pickup')], default='delivery', required=True)
    payment_method = fields.Selection([('cash', 'Cash'), ('online', 'Online'), ('wallet', 'Wallet'), ('aggregator', 'Aggregator Settlement')], default='cash', required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('received', 'Received'),
        ('needs_review', 'Needs Review'),
        ('accepted', 'Accepted'),
        ('preparing', 'Preparing'),
        ('ready', 'Ready'),
        ('out_for_delivery', 'Out For Delivery'),
        ('done', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True, tracking=True)
    line_ids = fields.One2many('anabtawi.direct.order.line', 'order_id', string='Lines', copy=True)
    driver_id = fields.Many2one('res.users', string='Driver')
    accepted_by_id = fields.Many2one('res.users', readonly=True)
    accepted_datetime = fields.Datetime(readonly=True)
    ready_datetime = fields.Datetime(readonly=True)
    delivered_datetime = fields.Datetime(readonly=True)
    requested_datetime = fields.Datetime(default=fields.Datetime.now)
    promised_datetime = fields.Datetime()
    notes = fields.Text()
    kitchen_notes = fields.Text()
    cancellation_reason = fields.Text()
    currency_id = fields.Many2one(related='company_id.currency_id', store=True, readonly=True)
    amount_untaxed = fields.Monetary(compute='_compute_amounts', store=True, currency_field='currency_id')
    amount_tax = fields.Monetary(compute='_compute_amounts', store=True, currency_field='currency_id')
    amount_delivery = fields.Monetary(compute='_compute_amounts', store=True, currency_field='currency_id')
    amount_discount = fields.Monetary(compute='_compute_amounts', store=True, currency_field='currency_id')
    amount_total = fields.Monetary(compute='_compute_amounts', store=True, currency_field='currency_id')
    sale_order_id = fields.Many2one('sale.order', readonly=True, copy=False)
    invoice_id = fields.Many2one('account.move', readonly=True, copy=False)
    pos_order_id = fields.Many2one('pos.order', readonly=True, copy=False)
    talabat_commission_amount = fields.Monetary(currency_field='currency_id')
    talabat_commission_percent = fields.Float(string='Commission %')
    commission_base_amount = fields.Monetary(compute='_compute_aggregator_accounting', store=True, currency_field='currency_id')
    commission_tax_amount = fields.Monetary(compute='_compute_aggregator_accounting', store=True, currency_field='currency_id')
    aggregator_discount_amount = fields.Monetary(string='Aggregator Contribution', currency_field='currency_id',
                                                help='Talabat-funded promotion/discount contribution. Store tax-excluded amount only.')
    company_discount_amount = fields.Monetary(string='Company Contribution', currency_field='currency_id',
                                             help='Anabtawi-funded promotion/discount contribution. Store tax-excluded amount only.')
    net_aggregator_receivable = fields.Monetary(compute='_compute_aggregator_accounting', store=True, currency_field='currency_id')
    aggregator_account_move_id = fields.Many2one('account.move', string='Aggregator Accounting Entry', readonly=True, copy=False)
    raw_payload = fields.Text(string='Raw API Payload')
    talabat_config_id = fields.Many2one('anabtawi.talabat.config', string='Talabat Configuration', copy=False)
    talabat_is_pro_order = fields.Boolean(string='Talabat Pro Order', copy=False)
    talabat_pro_fee_amount = fields.Monetary(string='Talabat Pro Fee', currency_field='currency_id', copy=False)
    talabat_vendor_id = fields.Char(copy=False)
    talabat_status = fields.Char(copy=False)
    talabat_last_sync = fields.Datetime(copy=False, readonly=True)
    talabat_sync_message = fields.Text(copy=False, readonly=True)
    kitchen_print_required = fields.Boolean(string='Kitchen Print Required', copy=False, readonly=True)
    notification_count = fields.Integer(compute='_compute_notification_count')
    prep_deadline = fields.Datetime(string='Preparation Deadline', copy=False)
    timer_status = fields.Selection([
        ('green', 'Green'),
        ('yellow', 'Yellow'),
        ('red', 'Red'),
    ], compute='_compute_timer_status', store=False)

    _sql_constraints = [
        ('external_order_ref_channel_unique', 'unique(channel, external_order_ref)', 'External order reference must be unique per channel.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('anabtawi.direct.order') or 'New'
            if vals.get('state') == 'draft':
                vals['state'] = 'received'
        orders = super().create(vals_list)
        orders._create_staff_notifications('new_order')
        return orders


    def _compute_notification_count(self):
        grouped = self.env['anabtawi.order.notification'].read_group(
            [('order_id', 'in', self.ids)], ['order_id'], ['order_id']
        )
        counts = {g['order_id'][0]: g['order_id_count'] for g in grouped}
        for order in self:
            order.notification_count = counts.get(order.id, 0)

    def _compute_timer_status(self):
        now = fields.Datetime.now()
        for order in self:
            branch = order.branch_id
            if not branch or not order.accepted_datetime:
                order.timer_status = 'green'
                continue
            accepted = fields.Datetime.from_string(order.accepted_datetime)
            elapsed_minutes = (fields.Datetime.from_string(now) - accepted).total_seconds() / 60.0 if isinstance(now, str) else (now - accepted).total_seconds() / 60.0
            if elapsed_minutes >= (branch.red_after_minutes or 20):
                order.timer_status = 'red'
            elif elapsed_minutes >= (branch.yellow_after_minutes or 10):
                order.timer_status = 'yellow'
            else:
                order.timer_status = 'green'

    @api.depends('line_ids.price_subtotal', 'line_ids.price_tax', 'line_ids.discount_amount', 'line_ids.is_delivery_fee')
    def _compute_amounts(self):
        for order in self:
            lines = order.line_ids
            order.amount_delivery = sum(lines.filtered('is_delivery_fee').mapped('price_subtotal'))
            order.amount_untaxed = sum(lines.mapped('price_subtotal'))
            order.amount_tax = sum(lines.mapped('price_tax'))
            order.amount_discount = sum(lines.mapped('discount_amount'))
            order.amount_total = order.amount_untaxed + order.amount_tax

    @api.depends('amount_total', 'amount_untaxed', 'talabat_commission_amount', 'talabat_commission_percent',
                 'aggregator_discount_amount', 'branch_id.commission_base', 'branch_id.default_commission_percent',
                 'branch_id.aggregator_commission_tax_id')
    def _compute_aggregator_accounting(self):
        for order in self:
            branch = order.branch_id
            commission_base = order.amount_total if branch.commission_base == 'tax_included' else order.amount_untaxed
            percent = order.talabat_commission_percent or branch.default_commission_percent or 0.0
            commission = order.talabat_commission_amount or (commission_base * percent / 100.0)
            tax_amount = 0.0
            if branch.aggregator_commission_tax_id and commission:
                taxes = branch.aggregator_commission_tax_id.compute_all(
                    commission,
                    currency=order.currency_id,
                    quantity=1.0,
                    product=False,
                    partner=order.partner_id,
                )
                tax_amount = sum(t.get('amount', 0.0) for t in taxes.get('taxes', []))
            order.commission_base_amount = commission_base
            order.commission_tax_amount = tax_amount
            # Expected Talabat/Careem settlement receivable from Odoo side. Sales tax is already part of amount_total
            # because tax is calculated after discount on order lines. Contributions are stored tax-excluded.
            order.net_aggregator_receivable = order.amount_total + order.aggregator_discount_amount - commission - tax_amount - order.talabat_pro_fee_amount

    def _get_commission_tax_account(self):
        self.ensure_one()
        tax = self.branch_id.aggregator_commission_tax_id
        if not tax:
            return False
        repartitions = tax.invoice_repartition_line_ids.filtered(lambda r: r.repartition_type == 'tax' and r.account_id)
        if repartitions:
            return repartitions[0].account_id
        return False

    def action_create_aggregator_accounting_entry(self):
        Move = self.env['account.move']
        for order in self:
            if order.aggregator_account_move_id:
                continue
            if order.channel not in ('talabat', 'careem'):
                continue
            branch = order.branch_id
            journal = branch.aggregator_accounting_journal_id or branch.receivable_journal_id or branch.sale_journal_id
            receivable_account = branch.aggregator_receivable_account_id
            commission_account = branch.aggregator_commission_account_id
            contribution_account = branch.aggregator_contribution_account_id
            company_discount_account = branch.company_discount_account_id
            if not journal or not receivable_account:
                raise UserError(_('Configure Aggregator Accounting Journal and Aggregator Receivable Account on branch %s.') % branch.display_name)
            line_vals = []
            commission = order.talabat_commission_amount or (order.commission_base_amount * (order.talabat_commission_percent or branch.default_commission_percent or 0.0) / 100.0)
            commission_tax = order.commission_tax_amount
            if commission:
                if not commission_account:
                    raise UserError(_('Configure Aggregator Commission Expense Account on branch %s.') % branch.display_name)
                line_vals.append((0, 0, {
                    'name': _('Talabat Commission - %s') % (order.external_order_ref or order.name),
                    'account_id': commission_account.id,
                    'debit': commission,
                    'credit': 0.0,
                    'partner_id': order.partner_id.id,
                }))
                if commission_tax:
                    tax_account = order._get_commission_tax_account()
                    if not tax_account:
                        raise UserError(_('Configure an account on the commission VAT/tax repartition for branch %s.') % branch.display_name)
                    line_vals.append((0, 0, {
                        'name': _('VAT on Talabat Commission - %s') % (order.external_order_ref or order.name),
                        'account_id': tax_account.id,
                        'debit': commission_tax,
                        'credit': 0.0,
                        'partner_id': order.partner_id.id,
                    }))
                line_vals.append((0, 0, {
                    'name': _('Deduct Talabat Commission from Settlement - %s') % (order.external_order_ref or order.name),
                    'account_id': receivable_account.id,
                    'debit': 0.0,
                    'credit': commission + commission_tax,
                    'partner_id': order.partner_id.id,
                }))
            if order.aggregator_discount_amount:
                if not contribution_account:
                    raise UserError(_('Configure Aggregator Contribution Recovery Account on branch %s.') % branch.display_name)
                line_vals.append((0, 0, {
                    'name': _('Talabat Contribution Recovery - %s') % (order.external_order_ref or order.name),
                    'account_id': receivable_account.id,
                    'debit': order.aggregator_discount_amount,
                    'credit': 0.0,
                    'partner_id': order.partner_id.id,
                }))
                line_vals.append((0, 0, {
                    'name': _('Talabat Funded Discount - %s') % (order.external_order_ref or order.name),
                    'account_id': contribution_account.id,
                    'debit': 0.0,
                    'credit': order.aggregator_discount_amount,
                    'partner_id': order.partner_id.id,
                }))
            if order.talabat_pro_fee_amount:
                pro_account = order.talabat_config_id.talabat_pro_fee_account_id if order.talabat_config_id else False
                if not pro_account:
                    raise UserError(_('Configure Talabat Pro Expense Account on the Talabat configuration.'))
                line_vals.append((0, 0, {
                    'name': _('Talabat Pro Fee - %s') % (order.external_order_ref or order.name),
                    'account_id': pro_account.id,
                    'debit': order.talabat_pro_fee_amount,
                    'credit': 0.0,
                    'partner_id': order.partner_id.id,
                }))
                line_vals.append((0, 0, {
                    'name': _('Deduct Talabat Pro Fee from Settlement - %s') % (order.external_order_ref or order.name),
                    'account_id': receivable_account.id,
                    'debit': 0.0,
                    'credit': order.talabat_pro_fee_amount,
                    'partner_id': order.partner_id.id,
                }))
            if order.company_discount_amount and company_discount_account:
                # Optional reporting-only entry for Anabtawi-funded contribution. The sale/POS line discount already
                # reduces taxable sales, so this entry is tax-excluded and does not create additional output tax.
                line_vals.append((0, 0, {
                    'name': _('Company Discount Contribution - %s') % (order.external_order_ref or order.name),
                    'account_id': company_discount_account.id,
                    'debit': order.company_discount_amount,
                    'credit': 0.0,
                    'partner_id': order.partner_id.id,
                }))
                line_vals.append((0, 0, {
                    'name': _('Company Discount Clearing - %s') % (order.external_order_ref or order.name),
                    'account_id': receivable_account.id,
                    'debit': 0.0,
                    'credit': order.company_discount_amount,
                    'partner_id': order.partner_id.id,
                }))
            if not line_vals:
                raise UserError(_('There is no aggregator commission/contribution amount to post for %s.') % order.name)
            debit = sum(line[2].get('debit', 0.0) for line in line_vals)
            credit = sum(line[2].get('credit', 0.0) for line in line_vals)
            diff = round(debit - credit, 2)
            if diff:
                # Avoid unbalanced moves caused by currency rounding.
                if diff > 0:
                    line_vals.append((0, 0, {
                        'name': _('Aggregator Accounting Rounding - %s') % order.name,
                        'account_id': receivable_account.id,
                        'debit': 0.0,
                        'credit': diff,
                        'partner_id': order.partner_id.id,
                    }))
                else:
                    line_vals.append((0, 0, {
                        'name': _('Aggregator Accounting Rounding - %s') % order.name,
                        'account_id': receivable_account.id,
                        'debit': abs(diff),
                        'credit': 0.0,
                        'partner_id': order.partner_id.id,
                    }))
            move = Move.create({
                'move_type': 'entry',
                'journal_id': journal.id,
                'date': fields.Date.context_today(order),
                'ref': '%s %s' % (order.channel.upper(), order.external_order_ref or order.name),
                'line_ids': line_vals,
            })
            order.aggregator_account_move_id = move.id
        return True


    def _has_available_stock(self):
        self.ensure_one()
        location = self.branch_id.stock_location_id or self.branch_id.warehouse_id.lot_stock_id
        if not location:
            return False
        for line in self.line_ids:
            if not line.product_id or line.product_id.type not in ('consu', 'product'):
                continue
            available_qty = line.product_id.with_context(location=location.id).qty_available
            if available_qty < line.quantity:
                return False
        return True

    def action_accept(self):
        now = fields.Datetime.now()
        for order in self:
            vals = {'state': 'accepted', 'accepted_by_id': self.env.user.id, 'accepted_datetime': now}
            if order.branch_id.default_preparation_minutes:
                vals['prep_deadline'] = fields.Datetime.add(now, minutes=order.branch_id.default_preparation_minutes)
            if order.branch_id.notify_auto_print or (order.talabat_config_id and order.talabat_config_id.auto_print_after_accept):
                vals['kitchen_print_required'] = True
            order.write(vals)
        self._create_staff_notifications('accepted')

    def action_prepare(self):
        self.write({'state': 'preparing'})
        self._create_staff_notifications('preparing')

    def action_ready(self):
        self.write({'state': 'ready', 'ready_datetime': fields.Datetime.now(), 'kitchen_print_required': False})
        self._create_staff_notifications('ready')

    def action_out_for_delivery(self):
        for order in self:
            if order.order_type == 'delivery' and not order.driver_id:
                raise UserError(_('Please assign a driver before sending the order out for delivery.'))
        self.write({'state': 'out_for_delivery'})
        self._create_staff_notifications('out_for_delivery')

    def action_done(self):
        self.write({'state': 'done', 'delivered_datetime': fields.Datetime.now()})
        self._create_staff_notifications('done')

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        self._create_staff_notifications('cancelled')


    def action_view_notifications(self):
        self.ensure_one()
        return {
            'name': _('Notifications'),
            'type': 'ir.actions.act_window',
            'res_model': 'anabtawi.order.notification',
            'view_mode': 'list,form',
            'domain': [('order_id', '=', self.id)],
            'context': {'default_order_id': self.id, 'default_branch_id': self.branch_id.id},
        }

    def _notification_message(self, event_type):
        self.ensure_one()
        source = dict(self._fields['channel'].selection).get(self.channel, self.channel)
        items = ', '.join('%s x %s' % (line.quantity, line.name or line.product_id.display_name) for line in self.line_ids[:5])
        if len(self.line_ids) > 5:
            items += ', ...'
        if event_type == 'new_order':
            return _('New %s order %s: %s') % (source, self.name, items or _('No lines'))
        if event_type == 'accepted':
            return _('%s accepted. Print kitchen ticket and start preparation.') % self.name
        if event_type == 'ready':
            return _('%s is ready for pickup/delivery.') % self.name
        if event_type == 'cancelled':
            return _('%s was cancelled.') % self.name
        return _('%s status changed to %s.') % (self.name, event_type)

    def _create_staff_notifications(self, event_type):
        Notification = self.env['anabtawi.order.notification'].sudo()
        for order in self:
            branch = order.branch_id
            if not branch:
                continue
            vals = {
                'name': '%s - %s' % (order.name, event_type.replace('_', ' ').title()),
                'order_id': order.id,
                'branch_id': branch.id,
                'event_type': event_type,
                'message': order._notification_message(event_type),
                'popup_required': branch.notify_pos_popup,
                'blocking_popup': branch.notify_blocking_popup and event_type == 'new_order',
                'sound_required': branch.notify_sound and event_type in ('new_order', 'ready', 'delayed'),
                'sound_type': branch.notify_sound_type,
                'repeat_until_ack': branch.notify_repeat_until_ack and event_type == 'new_order',
                'print_required': branch.notify_auto_print and event_type == 'accepted',
                'timer_required': branch.notify_timer_colors,
                'screen_required': branch.notify_screen_mode,
                'manager_alert_required': branch.notify_manager_activity or branch.notify_discuss_message or branch.notify_email,
                'priority': 'urgent' if event_type == 'new_order' else 'normal',
                'color_status': order.timer_status or 'green',
            }
            notification = Notification.create(vals)
            if vals['manager_alert_required']:
                order._notify_managers(notification)
        return True

    def _notify_managers(self, notification):
        self.ensure_one()
        managers = self.branch_id.notification_manager_user_ids
        if self.branch_id.notify_discuss_message:
            body = notification.message
            self.message_post(body=body, partner_ids=managers.mapped('partner_id').ids)
        if self.branch_id.notify_manager_activity and managers:
            activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
            for user in managers:
                self.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    user_id=user.id,
                    summary=_('Ordering notification'),
                    note=notification.message,
                )
        if self.branch_id.notify_email and managers:
            self.message_post(
                body=notification.message,
                partner_ids=managers.mapped('partner_id').ids,
                message_type='notification',
                subtype_xmlid='mail.mt_comment',
            )
        return True

    def action_create_sale_order(self):
        SaleOrder = self.env['sale.order']
        for order in self:
            if order.sale_order_id:
                continue
            partner = order.partner_id or self._create_or_get_partner(order)
            order_lines = []
            for line in order.line_ids:
                order_lines.append((0, 0, {
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.quantity,
                    'price_unit': line.price_unit,
                    'discount': line.discount_percent,
                    'name': line.name or line.product_id.display_name,
                }))
            so = SaleOrder.create({
                'partner_id': partner.id,
                'company_id': order.company_id.id,
                'origin': order.name,
                'client_order_ref': order.external_order_ref or order.name,
                'order_line': order_lines,
            })
            order.write({'partner_id': partner.id, 'sale_order_id': so.id})
        return True

    def action_push_talabat_status(self):
        status_map = {
            'accepted': 'accepted',
            'preparing': 'preparing',
            'ready': 'ready',
            'out_for_delivery': 'picked_up',
            'done': 'delivered',
            'cancelled': 'cancelled',
        }
        for order in self:
            if order.channel != 'talabat':
                continue
            if not order.talabat_config_id:
                raise UserError(_('Missing Talabat configuration on order %s.') % order.name)
            talabat_status = status_map.get(order.state)
            if not talabat_status:
                continue
            payload = {
                'order_id': order.external_order_ref,
                'status': talabat_status,
                'reason': order.cancellation_reason or False,
            }
            try:
                order.talabat_config_id._request('POST', '/orders/%s/status' % order.external_order_ref, payload=payload)
                order.write({
                    'talabat_status': talabat_status,
                    'talabat_last_sync': fields.Datetime.now(),
                    'talabat_sync_message': _('Status pushed successfully.'),
                })
            except Exception as exc:
                order.write({'talabat_sync_message': str(exc)})
                raise
        return True

    def _create_or_get_partner(self, order):
        partner = self.env['res.partner'].search([('phone', '=', order.customer_phone)], limit=1)
        if not partner:
            partner = self.env['res.partner'].create({
                'name': order.customer_name,
                'phone': order.customer_phone,
                'street': order.customer_address,
                'company_id': False,
            })
        return partner


class AnabtawiDirectOrderLine(models.Model):
    _name = 'anabtawi.direct.order.line'
    _description = 'Direct / Aggregator Order Line'
    _order = 'order_id, sequence, id'

    order_id = fields.Many2one('anabtawi.direct.order', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one('product.product', required=True)
    name = fields.Char()
    quantity = fields.Float(default=1.0)
    price_unit = fields.Monetary(required=True, currency_field='currency_id')
    discount_percent = fields.Float()
    discount_amount = fields.Monetary(compute='_compute_amounts', store=True, currency_field='currency_id')
    tax_ids = fields.Many2many('account.tax')
    price_subtotal = fields.Monetary(compute='_compute_amounts', store=True, currency_field='currency_id')
    price_tax = fields.Monetary(compute='_compute_amounts', store=True, currency_field='currency_id')
    price_total = fields.Monetary(compute='_compute_amounts', store=True, currency_field='currency_id')
    notes = fields.Char()
    external_line_ref = fields.Char()
    is_delivery_fee = fields.Boolean(default=False)
    currency_id = fields.Many2one(related='order_id.currency_id', store=True, readonly=True)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for line in self:
            if line.product_id:
                line.name = line.product_id.display_name
                line.price_unit = line.product_id.lst_price
                line.tax_ids = line.product_id.taxes_id

    @api.depends('quantity', 'price_unit', 'discount_percent', 'tax_ids')
    def _compute_amounts(self):
        for line in self:
            base = line.quantity * line.price_unit
            line.discount_amount = base * (line.discount_percent or 0.0) / 100.0
            subtotal = base - line.discount_amount
            taxes = line.tax_ids.compute_all(line.price_unit * (1 - (line.discount_percent or 0.0) / 100.0), currency=line.currency_id, quantity=line.quantity, product=line.product_id, partner=line.order_id.partner_id) if line.tax_ids else {'total_excluded': subtotal, 'total_included': subtotal, 'taxes': []}
            line.price_subtotal = taxes['total_excluded']
            line.price_tax = sum(t.get('amount', 0.0) for t in taxes.get('taxes', []))
            line.price_total = taxes['total_included']
