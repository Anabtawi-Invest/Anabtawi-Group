# -*- coding: utf-8 -*-

import logging
from datetime import date, datetime

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


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

    @api.model
    def _get_before_expiry_days(self):
        company_value = self.env.company.before_the_expiry_date
        if isinstance(company_value, datetime):
            # Keep compatibility with the existing field definition (Datetime) without schema changes.
            return max(company_value.day, 0)
        if isinstance(company_value, date):
            return max(company_value.day, 0)

        raw_value = self.env['ir.config_parameter'].sudo().get_param('before_the_expiry_date')
        try:
            return max(int(raw_value or 0), 0)
        except (TypeError, ValueError):
            _logger.warning("Invalid before_the_expiry_date value: %s", raw_value)
            return 0

    @api.model
    def _cron_notify_probation_expiry(self):
        days_before = self._get_before_expiry_days()
        today = fields.Date.context_today(self)
        target_expiry_date = today + relativedelta(days=days_before)
        summary = _("Probation Expiry Reminder")

        documents = self.sudo().search([
            ('document_type_id.is_probation_document', '=', True),
            ('expiry_date', '=', target_expiry_date),
            ('employee_id', '!=', False),
        ])
        if not documents:
            return

        hr_users = self.env.ref('hr.group_hr_user').sudo().users.filtered(
            lambda user: user.active and not user.share
        )
        if not hr_users:
            _logger.info("No active HR users found for probation expiry notification.")
            return

        todo_activity_type = self.env.ref('mail.mail_activity_data_todo')
        employee_model_id = self.env['ir.model']._get_id('hr.employee')

        for document in documents:
            employee = document.employee_id
            company = employee.company_id
            message = _(
                "Employee %(employee)s's probation period will expire on %(expiry)s."
            ) % {
                'employee': employee.name,
                'expiry': fields.Date.to_string(document.expiry_date),
            }
            users_to_notify = hr_users.filtered(
                lambda user: not company or company in user.company_ids
            )
            for user in users_to_notify:
                existing = self.env['mail.activity'].sudo().search_count([
                    ('res_model_id', '=', employee_model_id),
                    ('res_id', '=', employee.id),
                    ('user_id', '=', user.id),
                    ('activity_type_id', '=', todo_activity_type.id),
                    ('summary', '=', summary),
                    ('date_deadline', '=', today),
                ])
                if existing:
                    continue
                self.env['mail.activity'].sudo().create({
                    'res_model_id': employee_model_id,
                    'res_id': employee.id,
                    'user_id': user.id,
                    'activity_type_id': todo_activity_type.id,
                    'summary': summary,
                    'note': message,
                    'date_deadline': today,
                })
