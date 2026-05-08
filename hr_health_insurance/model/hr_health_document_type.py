# -*- coding: utf-8 -*-

from odoo import fields, models


class HrHealthDocumentType(models.Model):
    _name = 'hr.health.document.type'
    _description = 'Employee Document Type (Health Insurance)'
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True, translate=True)
    code = fields.Char(string='Code')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
