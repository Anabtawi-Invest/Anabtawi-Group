from odoo import api, fields, models, tools


class TanmyaPurchaseStageType(models.Model):
    _name = "tanmya.purchase.stage.type"
    _check_company_auto = True

    name = fields.Char(string='Purchase template', required=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    stages = fields.One2many('tanmya.purchase.stage', 'purchase_template', string='stages')
    minrange = fields.Float(string='From')
    maxrange = fields.Float(string='To')
    currency = fields.Many2one('res.currency', string='Currency', required=False)

    def get_stage_list(self):
        lst = []
        for rec in self.stages:
            lst.append(rec.code)
        return lst
