# -*- coding: utf-8 -*-

from odoo import fields, models


class HrAeDocumentType(models.Model):
    _name = "hr.ae.document.type"
    _description = "Employee document type (HR Enhancement)"
    _order = "sequence, id"

    name = fields.Char(string="Name", required=True, translate=True)
    code = fields.Char(string="Technical code", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("hr_ae_document_type_code_unique", "unique(code)", "Document type code must be unique."),
    ]
