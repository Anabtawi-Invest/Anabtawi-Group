# -*- coding: utf-8 -*-

from odoo import fields, models


class HrHealthEmployeeDocument(models.Model):
    _name = 'hr.health.employee.document'
    _description = 'Employee Document (Health Insurance)'
    _order = 'employee_id, document_type_id'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        ondelete='cascade',
        index=True,
    )
    document_type_id = fields.Many2one(
        'hr.health.document.type',
        string='Document Type',
        required=True,
        ondelete='restrict',
    )
    document_file = fields.Binary(string='File', attachment=True)
    document_filename = fields.Char(string='Filename')
    expiry_date = fields.Date(string='Expiry Date')

    _sql_constraints = [
        (
            'hr_health_employee_document_type_unique',
            'unique(employee_id, document_type_id)',
            'This document type is already attached to the employee.',
        ),
    ]
