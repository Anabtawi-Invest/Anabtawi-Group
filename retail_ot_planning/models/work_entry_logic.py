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

        for att in attendances:

            employee = att.employee_id
            start = att.check_in

            # Detect public holiday
            holiday = Holiday.search([
                ('date_from', '<=', start),
                ('date_to', '>=', start),
                ('resource_id', '=', False)
            ], limit=1)

            # Default label
            name = "Auto OT Entry"

            if holiday:
                name = "PHO Auto Entry"
            else:
                slot = Planning.search([
                    ('employee_id', '=', employee.id),
                    ('start_datetime', '<=', start),
                    ('end_datetime', '>=', start),
                ], limit=1)

                if not slot:
                    # Planned OFF day
                    name = "OTR Auto Entry"
                else:
                    # Planned working day
                    name = "OTW Auto Entry"

            # SAFE duplicate protection (NO DATE FIELDS)
            existing = WorkEntry.search([
                ('employee_id', '=', employee.id),
                ('name', '=', name),
            ], limit=1)

            if not existing:
                WorkEntry.create({
                    'name': name,
                    'employee_id': employee.id,
                })
