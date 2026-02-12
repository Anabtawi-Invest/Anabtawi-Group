from odoo import models, fields, api


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # =====================================================
    # ENTERPRISE Lateness + OT Fields
    # =====================================================

    lateness_hours = fields.Float(
        string="Lateness Hours",
        compute="_compute_lateness_ot",
        store=True,
    )

    ot_hours = fields.Float(
        string="OT Hours",
        compute="_compute_lateness_ot",
        store=True,
    )

    ot_bank = fields.Float(
        string="OT Bank",
        compute="_compute_lateness_ot",
        store=True,
    )

    remaining_hours = fields.Float(
        string="Remaining Lateness",
        compute="_compute_lateness_ot",
        store=True,
    )

    # =====================================================
    # COMPUTE USING WORK ENTRY TYPES (SAFE FOR ODOO 19)
    # =====================================================

    @api.depends("work_entry_ids")
    def _compute_lateness_ot(self):

        for slip in self:

            lateness = 0.0
            ot_total = 0.0

            for entry in slip.work_entry_ids:

                code = entry.work_entry_type_id.display_code
                hours = entry.duration or 0.0

                if code == "LAT":
                    lateness += hours

                if code in ("OTW", "OTR", "PHO"):
                    ot_total += hours

            slip.lateness_hours = lateness
            slip.ot_hours = ot_total
            slip.ot_bank = ot_total
            slip.remaining_hours = max(lateness - ot_total, 0.0)
