from odoo import api, fields, models, tools
from odoo.exceptions import ValidationError


class tanmya_PurchaseStage(models.Model):
    _name = "tanmya.purchase.stage"

    code = fields.Char(string='Stage code', required=True)
    name = fields.Char(string='Stage name', required=True)
    stageusers = fields.Many2many('res.users', string='Related users')
    purchase_template = fields.Many2one('tanmya.purchase.stage.type', string='Purchase template', required=False)
    company_id = fields.Many2one(
        related='purchase_template.company_id',
        string='Company',
        store=True,
        readonly=True,
        index=True,
    )
    stageorder = fields.Integer(string='Stage Rank', required=True)
    issystem = fields.Boolean(string='internal', default=False, invisible=True)
    approvetype = fields.Selection([
        ('sequence', 'sequence'),
        ('anyone', 'anyone'),
        ('parallel', 'parallel'),
    ], string='Approve Mode', default='sequence')

    @api.constrains('code', 'purchase_template')
    def _check_code_unique_per_template(self):
        """Allow the same code across companies/templates; block duplicates inside one template."""
        for rec in self:
            if not rec.code or not rec.purchase_template:
                continue
            duplicate = self.search([
                ('id', '!=', rec.id),
                ('code', '=', rec.code),
                ('purchase_template', '=', rec.purchase_template.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(
                    'Stage code already exists on this purchase template!'
                )
