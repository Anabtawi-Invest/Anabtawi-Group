from odoo import api, fields, models, _

class PosConfig(models.Model):
    _inherit = 'pos.config'

    pos_allowed_user_ids = fields.Many2many('res.users','res_user_config_rel', string='Allowed Users',index=True)
    