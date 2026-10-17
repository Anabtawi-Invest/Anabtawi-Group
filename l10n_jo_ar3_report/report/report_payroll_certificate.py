# -*- coding: utf-8 -*-
from datetime import date

from odoo import models


class PayrollCertificateReport(models.AbstractModel):
    _name = 'report.l10n_jo_ar3_report.template_pwts_report'
    _description = 'Jordan AR/3 Payroll Certificate Report'

    def _get_report_values(self, docids, data=None):
        docs = self.env['payroll.report.wizard'].browse(docids)
        result = []
        for doc in docs:
            result.append(doc._prepare_report_data())

        return {
            'doc_ids': docids,
            'doc_model': 'payroll.report.wizard',
            'docs': docs,
            'data': result[0] if result else {},
            'report_date': date.today().strftime('%Y-%m-%d'),
        }
