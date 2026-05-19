from odoo import api, fields, models, tools


class tanmya_PurchaseStage(models.Model):
    _name = "tanmya.purchase.stage"
    code = fields.Char(string='Stage code', required=True)
    name = fields.Char(string='Stage name', required=True)
    stageusers = fields.Many2many('res.users', string='Related users')
    purchase_template = fields.Many2one('tanmya.purchase.stage.type', string='Purchase template', required=False)
    stageorder = fields.Integer(string='Stage Rank',required=True)
    _sql_constraints = [
        ('tanmya_stage_code_unique', 'unique(code)', 'stage code already exists!')
    ]
    issystem = fields.Boolean(string='internal', default=False, invisible=True)
    approvetype = fields.Selection([
        ('sequence', 'sequence'),
        ('anyone', 'anyone'),

        ('parallel', 'parallel')], string='Approve Mode',
                                   default='sequence')

