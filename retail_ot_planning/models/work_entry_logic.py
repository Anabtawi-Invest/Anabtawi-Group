from odoo import models


class HrContract(models.Model):
    _inherit = "hr.contract"

    def _get_work_entries_values(self, date_start, date_stop):

        # Get native work entries first
        res = super()._get_work_entries_values(date_start, date_stop)

        Planning = self.env['planning.slot']
        Holiday = self.env['resource.calendar.leaves']

        for entry in res:

            employee_id = entry.get('employee_id')
            start = entry.get('date_start') or entry.get('date_from')

            if not employee_id or not start:
                continue

            # Detect holiday
            holiday = Holiday.search([
                ('date_from', '<=', start),
                ('date_to', '>=', start),
                ('resource_id', '=', False)
            ], limit=1)

            if holiday:
                entry['name'] = "PHO Auto Entry"
                continue

            # Detect planning slot
            slot = Planning.search([
                ('employee_id', '=', employee_id),
                ('start_datetime', '<=', start),
                ('end_datetime', '>=', start),
            ], limit=1)

            if not slot:
                entry['name'] = "OTR Auto Entry"
            else:
                entry['name'] = "OTW Auto Entry"

        return res
