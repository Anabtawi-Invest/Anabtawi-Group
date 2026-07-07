from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AnabtawiOrderingBranch(models.Model):
    _name = 'anabtawi.ordering.branch'
    _description = 'Direct Ordering Branch Configuration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    pos_config_id = fields.Many2one('pos.config', string='POS Configuration')
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')
    stock_location_id = fields.Many2one('stock.location', string='Stock Location')
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    sale_journal_id = fields.Many2one('account.journal', string='Sales Journal', domain="[('type','=','sale')]")
    cash_journal_id = fields.Many2one('account.journal', string='Cash Journal')
    receivable_journal_id = fields.Many2one('account.journal', string='Online Receivable Journal')
    aggregator_accounting_journal_id = fields.Many2one(
        'account.journal',
        string='Aggregator Accounting Journal',
        domain="[('type','in',('general','sale'))]",
        help='Journal used for Talabat/Careem settlement adjustment entries. This does not change Talabat API behavior.'
    )
    aggregator_receivable_account_id = fields.Many2one(
        'account.account',
        string='Aggregator Receivable Account',
        help='Receivable/clearing account for amounts due from Talabat or other aggregators.'
    )
    aggregator_commission_account_id = fields.Many2one(
        'account.account',
        string='Aggregator Commission Expense Account',
        help='Expense account used to post Talabat commission separately from sales.'
    )
    aggregator_commission_tax_id = fields.Many2one(
        'account.tax',
        string='Commission VAT / Tax',
        domain="[('type_tax_use','in',('purchase','none'))]",
        help='Tax applied on aggregator commission fees, if Talabat charges VAT on commission.'
    )
    aggregator_contribution_account_id = fields.Many2one(
        'account.account',
        string='Aggregator Contribution Recovery Account',
        help='Account credited when Talabat funds part of a promotion/discount. Amounts are posted tax-excluded.'
    )
    company_discount_account_id = fields.Many2one(
        'account.account',
        string='Company Discount Expense Account',
        help='Optional account for reporting Anabtawi-funded discount amounts. Amounts are recorded tax-excluded and not included in sales tax.'
    )
    commission_base = fields.Selection([
        ('tax_included', 'Commission on Total Including Tax'),
        ('tax_excluded', 'Commission on Total Excluding Tax'),
    ], string='Commission Base', default='tax_included', required=True,
       help='Controls Odoo-side Talabat commission calculation. Talabat API mapping is not changed.')
    default_commission_percent = fields.Float(
        string='Default Aggregator Commission %',
        default=20.0,
        help='Used only when the imported Talabat order does not provide an explicit commission amount.'
    )
    opening_time = fields.Float(default=9.0)
    closing_time = fields.Float(default=24.0)
    allow_pickup = fields.Boolean(default=True)
    allow_delivery = fields.Boolean(default=True)
    default_preparation_minutes = fields.Integer(default=30)
    min_order_amount = fields.Monetary(currency_field='currency_id')
    delivery_fee_product_id = fields.Many2one('product.product', string='Delivery Fee Product')
    currency_id = fields.Many2one(related='company_id.currency_id', store=True, readonly=True)
    zone_ids = fields.One2many('anabtawi.delivery.zone', 'branch_id', string='Delivery Zones')

    # Staff notification configuration. Each branch can enable one option, several options, or all options.
    notify_pos_popup = fields.Boolean(string='POS Popup', default=True)
    notify_blocking_popup = fields.Boolean(string='Blocking Popup Until Action', default=True)
    notify_sound = fields.Boolean(string='Sound Alert', default=True)
    notify_sound_type = fields.Selection([
        ('bell', 'Bell'),
        ('buzzer', 'Kitchen Buzzer'),
        ('voice', 'Voice Announcement'),
        ('silent', 'Silent'),
    ], string='Sound Type', default='bell')
    notify_repeat_until_ack = fields.Boolean(string='Repeat Until Accepted/Acknowledged', default=True)
    notify_auto_print = fields.Boolean(string='Auto Kitchen Print Flag', default=True)
    notify_timer_colors = fields.Boolean(string='Preparation Timer Colors', default=True)
    notify_screen_mode = fields.Boolean(string='Branch Announcement Screen', default=False)
    notify_manager_activity = fields.Boolean(string='Manager Odoo Activity', default=False)
    notify_discuss_message = fields.Boolean(string='Odoo Discuss Message', default=False)
    notify_email = fields.Boolean(string='Manager Email', default=False)
    notification_manager_user_ids = fields.Many2many('res.users', 'anabtawi_ordering_branch_manager_notify_rel', 'branch_id', 'user_id', string='Notification Managers')
    yellow_after_minutes = fields.Integer(string='Yellow After Minutes', default=10)
    red_after_minutes = fields.Integer(string='Red After Minutes', default=20)

    @api.constrains('opening_time', 'closing_time')
    def _check_times(self):
        for rec in self:
            if rec.opening_time < 0 or rec.closing_time <= 0 or rec.closing_time > 24:
                raise ValidationError(_('Opening and closing times must be between 0 and 24.'))



    def action_send_test_notification(self):
        Notification = self.env['anabtawi.order.notification'].sudo()
        for branch in self:
            Notification.create({
                'name': _('Test Notification - %s') % branch.name,
                'branch_id': branch.id,
                'event_type': 'test',
                'message': _('This is a test order notification for %s. If POS polling is enabled, the branch POS should show it.') % branch.name,
                'popup_required': branch.notify_pos_popup,
                'blocking_popup': branch.notify_blocking_popup,
                'sound_required': branch.notify_sound,
                'sound_type': branch.notify_sound_type,
                'repeat_until_ack': branch.notify_repeat_until_ack,
                'print_required': branch.notify_auto_print,
                'timer_required': branch.notify_timer_colors,
                'screen_required': branch.notify_screen_mode,
                'manager_alert_required': branch.notify_manager_activity or branch.notify_discuss_message or branch.notify_email,
                'priority': 'normal',
            })
        return True

class AnabtawiDeliveryZone(models.Model):
    _name = 'anabtawi.delivery.zone'
    _description = 'Direct Ordering Delivery Zone'
    _order = 'branch_id, name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    branch_id = fields.Many2one('anabtawi.ordering.branch', required=True, ondelete='cascade')
    delivery_fee = fields.Monetary(currency_field='currency_id')
    min_order_amount = fields.Monetary(currency_field='currency_id')
    estimated_minutes = fields.Integer(default=45)
    currency_id = fields.Many2one(related='branch_id.currency_id', store=True, readonly=True)
