
from odoo import models, api

class RetailOTAutomation(models.Model):
    _inherit = "hr.work.entry"

    @api.model
    def run_planning_ot_logic(self):

        attendances = self.env['hr.attendance'].search([
            ('check_out', '!=', False)
        ])

        WorkEntry = self.env['hr.work.entry']
        Planning = self.env['planning.slot']
        Holiday = self.env['resource.calendar.leaves']

        # NOTE:
        # Replace these external IDs with your real Work Entry Type XMLIDs
        OTW = self.env.ref('hr_work_entry_contract.work_entry_type_attendance')
        OTR = self.env.ref('hr_work_entry_contract.work_entry_type_leave')
        PHO = self.env.ref('hr_work_entry_contract.work_entry_type_global_leave')

        for att in attendances:

            employee = att.employee_id
            start = att.check_in
            end = att.check_out

            # Check public holiday
            holiday = Holiday.search([
                ('date_from', '<=', start),
                ('date_to', '>=', start),
                ('resource_id', '=', False)
            ], limit=1)

            if holiday:
                work_type = PHO
            else:
                # Check planning slot
                slot = Planning.search([
                    ('employee_id', '=', employee.id),
                    ('start_datetime', '<=', start),
                    ('end_datetime', '>=', start),
                ], limit=1)

                if not slot:
                    # Planned OFF day -> Weekend OT
                    work_type = OTR
                else:
                    # Planned working day (example uses OTW placeholder)
                    work_type = OTW

            # Avoid duplicates
            existing = WorkEntry.search([
                ('employee_id', '=', employee.id),
                ('date_start', '=', start),
                ('date_stop', '=', end),
                ('work_entry_type_id', '=', work_type.id),
            ], limit=1)

            if not existing:
                WorkEntry.create({
                    'name': 'Auto OT Entry',
                    'employee_id': employee.id,
                    'date_start': start,
                    'date_stop': end,
                    'work_entry_type_id': work_type.id,
                })
