# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


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
    probation_start_date = fields.Date(string='Probation Start Date')
    expiry_date = fields.Date(string='Expiry Date')

    _sql_constraints = [
        (
            'hr_health_employee_document_type_unique',
            'unique(employee_id, document_type_id)',
            'This document type is already attached to the employee.',
        ),
    ]

    @api.onchange('document_type_id', 'probation_start_date')
    def _onchange_probation_dates(self):
        self._sync_probation_expiry_date()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get('skip_probation_expiry_sync'):
            records._sync_probation_expiry_date()
        return records

    def write(self, vals):
        result = super().write(vals)
        if (
            not self.env.context.get('skip_probation_expiry_sync')
            and {'document_type_id', 'probation_start_date'} & set(vals)
        ):
            self._sync_probation_expiry_date()
        return result

    def _sync_probation_expiry_date(self):
        probation_docs = self.filtered('document_type_id.is_probation_document')
        for document in probation_docs:
            expected_expiry = (
                document.probation_start_date + relativedelta(months=3)
                if document.probation_start_date else False
            )
            if document.expiry_date != expected_expiry:
                if document._origin and document._origin.id:
                    super(HrHealthEmployeeDocument, document.with_context(skip_probation_expiry_sync=True)).write({
                        'expiry_date': expected_expiry,
                    })
                else:
                    document.expiry_date = expected_expiry
