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
        records.filtered('document_file')._sync_file_to_employee_documents()
        return records

    def write(self, vals):
        result = super().write(vals)
        if (
            not self.env.context.get('skip_probation_expiry_sync')
            and {'document_type_id', 'probation_start_date'} & set(vals)
        ):
            self._sync_probation_expiry_date()
        if vals.get('document_file'):
            self._sync_file_to_employee_documents()
        return result

    def _documents_file_extension(self):
        """Prefer the uploaded filename extension, then the stored attachment name."""
        self.ensure_one()
        for candidate in (self.document_filename,):
            if candidate and '.' in candidate:
                return candidate.rsplit('.', 1)[-1]
        attachment = self._get_document_file_attachment()
        if attachment and attachment.name and '.' in attachment.name:
            return attachment.name.rsplit('.', 1)[-1]
        return ''

    def _documents_display_name(self):
        """Name shown in Documents: document type (+ extension when available)."""
        self.ensure_one()
        base_name = (self.document_type_id.name or _('Document')).strip()
        extension = self._documents_file_extension()
        return f'{base_name}.{extension}' if extension else base_name

    def _documents_unique_name(self, folder, desired_name):
        """Keep prior uploads: append (2), (3), ... when the name already exists."""
        Document = self.env['documents.document'].sudo()
        existing = set(Document.search([
            ('folder_id', '=', folder.id),
            ('type', '=', 'binary'),
        ]).mapped('name'))
        if desired_name not in existing:
            return desired_name
        if '.' in desired_name:
            stem, extension = desired_name.rsplit('.', 1)
            suffix = f'.{extension}'
        else:
            stem, suffix = desired_name, ''
        index = 2
        while True:
            candidate = f'{stem} ({index}){suffix}'
            if candidate not in existing:
                return candidate
            index += 1

    def _get_document_file_attachment(self):
        self.ensure_one()
        return self.env['ir.attachment'].sudo().search([
            ('res_model', '=', self._name),
            ('res_field', '=', 'document_file'),
            ('res_id', '=', self.id),
        ], limit=1)

    def _ensure_employee_documents_folder(self):
        """Reuse documents_hr employee folder; create it if HR Documents is configured."""
        self.ensure_one()
        employee = self.employee_id
        if not employee:
            return self.env['documents.document']
        company = employee.company_id
        if not company.documents_hr_settings or not company.documents_employee_folder_id:
            return self.env['documents.document']
        if not employee.hr_employee_folder_id:
            employee._generate_employee_documents_folders()
        return employee.hr_employee_folder_id

    def _sync_file_to_employee_documents(self):
        """Copy each uploaded Binary into Documents under the employee folder.

        Uses a copied attachment so re-uploads keep older Documents versions.
        """
        if self.env.context.get('skip_documents_sync'):
            return
        Document = self.env['documents.document'].sudo()
        for record in self:
            if not record.document_file:
                continue
            folder = record._ensure_employee_documents_folder()
            if not folder:
                _logger.info(
                    "Skip Documents sync for employee document %s: no HR employee folder "
                    "(enable Documents HR settings / employee root folder).",
                    record.id,
                )
                continue
            field_attachment = record._get_document_file_attachment()
            if not field_attachment or not field_attachment.datas:
                continue

            doc_name = record._documents_unique_name(folder, record._documents_display_name())
            # Detached copy: Binary field attachment is overwritten in place on re-upload.
            documents_attachment = field_attachment.with_context(no_document=True).copy({
                'name': doc_name,
                'res_model': False,
                'res_id': False,
                'res_field': False,
            })
            Document.create({
                'name': doc_name,
                'type': 'binary',
                'folder_id': folder.id,
                'attachment_id': documents_attachment.id,
                'company_id': record.employee_id.company_id.id,
                'partner_id': record.employee_id.work_contact_id.id or False,
            })

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
