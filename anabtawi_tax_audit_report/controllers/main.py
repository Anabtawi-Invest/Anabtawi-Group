import base64
from odoo import http
from odoo.http import request


class TaxAuditReportController(http.Controller):

    @http.route('/anabtawi_tax_audit/download_excel', type='http', auth='user')
    def download_excel(self, wizard_id, **kw):
        wizard = request.env['tax.audit.report.wizard'].browse(int(wizard_id))
        if not wizard.exists():
            return request.not_found()

        if not wizard.excel_file:
            excel_bytes = wizard._generate_excel_workbook()
            file_content = excel_bytes
        else:
            file_content = base64.b64decode(wizard.excel_file)

        filename = wizard.filename or f"Tax_Audit_Report_{wizard.id}.xlsx"
        
        headers = [
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition', http.content_disposition(filename)),
        ]
        return request.make_response(file_content, headers=headers)
