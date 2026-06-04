from odoo import _, http
from odoo.http import content_disposition, request
from odoo.tools import osutil


class InternalTransferXlsxController(http.Controller):
    @http.route(
        ['/internal_transfer_excel_report/xlsx/<int:wizard_id>'],
        type='http',
        auth='user',
    )
    def download_internal_transfer_xlsx(self, wizard_id, **kwargs):
        lang = request.env.user.lang or request.context.get('lang')
        wizard = request.env['internal.transfer.report.wizard'].with_context(lang=lang).browse(wizard_id)
        if not wizard.exists():
            return request.not_found()

        xlsx_data = wizard._generate_xlsx_content()
        filename = osutil.clean_filename(wizard.env._("Internal Transfer Report") + '.xlsx')
        headers = [
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition', content_disposition(filename)),
        ]
        return request.make_response(xlsx_data, headers=headers)
