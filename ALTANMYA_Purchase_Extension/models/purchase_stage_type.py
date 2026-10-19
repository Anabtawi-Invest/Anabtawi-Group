from odoo import api, fields, models, tools


class TanmyaPurchaseStageType(models.Model):
    _name = "tanmya.purchase.stage.type"
    name = fields.Char(string='Purchase template', required=True)
    stages = fields.One2many('tanmya.purchase.stage', 'purchase_template', string='stages')
    minrange=fields.Float(string='From')
    maxrange=fields.Float(string='To')
    currency=fields.Many2one('res.currency',string='Currency',required=False)


    def get_stage_list(self):
        lst=[]
        for rec in self.stages:
            lst.append(rec.code)
        return lst

