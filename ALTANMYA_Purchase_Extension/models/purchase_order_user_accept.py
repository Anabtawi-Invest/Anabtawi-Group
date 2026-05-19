from odoo import api, fields, models, tools

class TanmyaPurchaseOrderAccept(models.Model):
    _name = "tanmya.purchase.order.pending"
    user=fields.Many2one('res.users',string='user')
    purchaseorder=fields.Many2one('purchase.order',  string='purchase order')
    state=fields.Char(string='stage')
    status=fields.Selection(selection=[
            ('approve', 'Approve'),
            ('decline', 'Decline'),
            ('queue', 'Queue'),
            ('waiting', 'Waiting'),
        ],default='waiting')
    userorder=fields.Integer(string ='user order',default=0)