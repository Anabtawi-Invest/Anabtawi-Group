from odoo import _, http
from odoo.http import content_disposition, request
from odoo.tools import osutil


class PosDailyOperationsXlsxController(http.Controller):
    @http.route(
        ['/pos_daily_operations_report/xlsx/<int:wizard_id>'],
        type='http',
        auth='user',
    )
    def download_pos_daily_operations_xlsx(self, wizard_id, **kwargs):
        wizard = request.env['pos.daily.operations.wizard'].browse(wizard_id)
        if not wizard.exists():
            return request.not_found()

        xlsx_data = wizard._generate_xlsx_content()
        filename = osutil.clean_filename(_('Daily Operations Summary') + '.xlsx')
        headers = [
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition', content_disposition(filename)),
        ]
        return request.make_response(xlsx_data, headers=headers)
