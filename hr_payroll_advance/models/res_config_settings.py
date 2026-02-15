# -*- coding: utf-8 -*-
from odoo import api, fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pce_annual_leave_type_id = fields.Many2one(
        "hr.leave.type",
        string="Annual Leave Type (for lateness offset)",
        help="Used when remaining lateness hours (after OT bank) should be deducted from Annual Leave.",
    )
    pce_lateness_code = fields.Char(
        string="Lateness Worked Days Code",
        default="LAT",
        help="Worked Days code used by your Work Entry type for lateness (e.g. LAT).",
    )
    pce_ot_codes = fields.Char(
        string="OT Worked Days Codes",
        default="OTW,OTR,PHO",
        help="Comma-separated worked days codes for overtime (e.g. OTW,OTR,PHO).",
    )
    pce_default_month_hours = fields.Float(
        string="Fallback Month Hours (hourly rate)",
        default=173.33,
        help="Used to compute hourly rate if the payslip has no regular worked hours line.",
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        ICP = self.env["ir.config_parameter"].sudo()
        res.update(
            pce_annual_leave_type_id=int(ICP.get_param("pce.annual_leave_type_id", "0") or 0) or False,
            pce_lateness_code=ICP.get_param("pce.lateness_code", "LAT"),
            pce_ot_codes=ICP.get_param("pce.ot_codes", "OTW,OTR,PHO"),
            pce_default_month_hours=float(ICP.get_param("pce.default_month_hours", "173.33") or 173.33),
        )
        return res

    def set_values(self):
        super().set_values()
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("pce.annual_leave_type_id", self.pce_annual_leave_type_id.id or 0)
        ICP.set_param("pce.lateness_code", self.pce_lateness_code or "LAT")
        ICP.set_param("pce.ot_codes", self.pce_ot_codes or "OTW,OTR,PHO")
        ICP.set_param("pce.default_month_hours", self.pce_default_month_hours or 173.33)
