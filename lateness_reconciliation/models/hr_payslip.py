# -*- coding: utf-8 -*-
##############################################################################
# Lateness Reconciliation - Odoo 19 Online Compatible Version
# This version fixes invalid domain errors caused by deprecated fields
# Compatible with Odoo Online (no Odoo.sh required)
##############################################################################

from odoo import models, fields, api


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    lateness_hours = fields.Float(
        string="Lateness Hours",
        compute="_compute_lateness_hours",
        store=True,
        help="Total lateness hours calculated from work entries within the payslip period."
    )

    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_lateness_hours(self):
        """
        Compute total lateness hours for each payslip.

        IMPORTANT:
        - Odoo 19 Online hr.work.entry uses:
              'date'      (date field)
              'duration'  (float)
        - It does NOT use 'date_start' or 'date_stop'
        - Using invalid fields causes payroll batch crash

        This method is safe for payroll batch generation.
        """

        WorkEntry = self.env['hr.work.entry']

        for slip in self:
            # Default safe value
            total_lateness = 0.0

            # Safety checks to avoid computation crash
            if not slip.employee_id:
                slip.lateness_hours = 0.0
                continue

            if not slip.date_from or not slip.date_to:
                slip.lateness_hours = 0.0
                continue

            # Search work entries using correct Odoo 19 fields
            entries = WorkEntry.search([
                ('employee_id', '=', slip.employee_id.id),
                ('date', '>=', slip.date_from),
                ('date', '<=', slip.date_to),
            ])

            # ------------------------------------------------------------
            # IMPORTANT:
            # If you have a specific Work Entry Type for Lateness
            # (example: code = 'LATE'), uncomment and adjust below.
            # ------------------------------------------------------------

            for entry in entries:
                # Example filter (UNCOMMENT if needed):
                # if entry.work_entry_type_id.code == 'LATE':
                #     total_lateness += entry.duration

                # If all matching entries represent lateness:
                total_lateness += entry.duration or 0.0

            # Assign computed value safely
            slip.lateness_hours = total_lateness
