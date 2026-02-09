from odoo import fields, models

class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    late_reco_late_hours = fields.Float(string="Late Hours", readonly=True)
    late_reco_ot_hours = fields.Float(string="OT Used", readonly=True)
    late_reco_al_hours = fields.Float(string="AL Used", readonly=True)
    late_reco_unpaid_hours = fields.Float(string="Unpaid Hours", readonly=True)
