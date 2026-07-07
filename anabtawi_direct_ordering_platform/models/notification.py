from odoo import api, fields, models, _


class AnabtawiOrderNotification(models.Model):
    _name = 'anabtawi.order.notification'
    _description = 'Ordering POS / Staff Notification'
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'

    name = fields.Char(required=True, default='New Notification')
    order_id = fields.Many2one('anabtawi.direct.order', ondelete='cascade', index=True)
    branch_id = fields.Many2one('anabtawi.ordering.branch', required=True, index=True)
    pos_config_id = fields.Many2one('pos.config', related='branch_id.pos_config_id', store=True, readonly=True)
    channel = fields.Selection(related='order_id.channel', store=True, readonly=True)
    event_type = fields.Selection([
        ('new_order', 'New Order'),
        ('accepted', 'Accepted'),
        ('preparing', 'Preparing'),
        ('ready', 'Ready'),
        ('out_for_delivery', 'Out For Delivery'),
        ('done', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('delayed', 'Delayed'),
        ('test', 'Test'),
    ], required=True, default='new_order', index=True)
    state = fields.Selection([
        ('new', 'New'),
        ('shown', 'Shown'),
        ('acknowledged', 'Acknowledged'),
        ('dismissed', 'Dismissed'),
    ], default='new', index=True)
    message = fields.Text(required=True)
    popup_required = fields.Boolean(default=False)
    sound_required = fields.Boolean(default=False)
    print_required = fields.Boolean(default=False)
    timer_required = fields.Boolean(default=False)
    manager_alert_required = fields.Boolean(default=False)
    screen_required = fields.Boolean(default=False)
    blocking_popup = fields.Boolean(default=False)
    repeat_until_ack = fields.Boolean(default=False)
    sound_type = fields.Selection([
        ('bell', 'Bell'),
        ('buzzer', 'Kitchen Buzzer'),
        ('voice', 'Voice Announcement'),
        ('silent', 'Silent'),
    ], default='bell')
    priority = fields.Selection([
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ], default='normal', index=True)
    color_status = fields.Selection([
        ('green', 'Green'),
        ('yellow', 'Yellow'),
        ('red', 'Red'),
    ], default='green')
    acknowledged_by_id = fields.Many2one('res.users', readonly=True)
    acknowledged_datetime = fields.Datetime(readonly=True)
    payload_json = fields.Text(string='Technical Payload')

    def action_mark_shown(self):
        self.filtered(lambda n: n.state == 'new').write({'state': 'shown'})
        return True

    def action_acknowledge(self):
        self.write({
            'state': 'acknowledged',
            'acknowledged_by_id': self.env.user.id,
            'acknowledged_datetime': fields.Datetime.now(),
        })
        return True

    def action_dismiss(self):
        self.write({'state': 'dismissed'})
        return True
