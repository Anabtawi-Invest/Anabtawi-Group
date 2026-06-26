from odoo import _, api, fields, models


class ReportPosPaymentSummary(models.AbstractModel):
    _name = 'report.pos_payment_summary_report.report_payment_summary'
    _description = 'POS Payment Summary Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = dict(data or {})
        wizard = self.env['pos.payment.summary.wizard'].browse(data.get('wizard_id') or docids)
        if not wizard:
            wizard = self.env['pos.payment.summary.wizard'].browse(docids)
        wizard = wizard[:1]
        if not wizard:
            return {
                'doc_ids': [],
                'doc_model': 'pos.payment.summary.wizard',
                'docs': self.env['pos.payment.summary.wizard'],
                'lines': [],
                'date_from': data.get('date_from'),
                'date_to': data.get('date_to'),
                'pos_config_name': data.get('pos_config_name'),
            }

        return {
            'doc_ids': wizard.ids,
            'doc_model': 'pos.payment.summary.wizard',
            'docs': wizard,
            'lines': wizard._get_report_lines(),
            'date_from': data.get('date_from') or fields.Date.to_string(wizard.date_from),
            'date_to': data.get('date_to') or fields.Date.to_string(wizard.date_to),
            'pos_config_name': data.get('pos_config_name') or (
                wizard.pos_config_id.name if wizard.pos_config_id else _('All POS')
            ),
        }
