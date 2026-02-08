# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    prr_lateness_work_entry_type_id = fields.Many2one(
        "hr.work.entry.type",
        string="Lateness Work Entry Type",
        help="Work entry type used to represent lateness (hours).",
    )

    prr_ot_work_entry_type_ids = fields.Many2many(
        "hr.work.entry.type",
        "company_prr_ot_work_entry_type_rel",
        "company_id",
        "type_id",
        string="OT Work Entry Types (Bank)",
        help="Work entry types that represent banked overtime hours available for reconciliation.",
    )

    prr_annual_leave_type_id = fields.Many2one(
        "hr.leave.type",
        string="Annual Leave Type (Hours)",
        help="Time Off type representing Annual Leave. Must support hour-based requests/allocations.",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    prr_lateness_work_entry_type_id = fields.Many2one(
        related="company_id.prr_lateness_work_entry_type_id",
        readonly=False,
    )
    prr_ot_work_entry_type_ids = fields.Many2many(
        related="company_id.prr_ot_work_entry_type_ids",
        readonly=False,
    )
    prr_annual_leave_type_id = fields.Many2one(
        related="company_id.prr_annual_leave_type_id",
        readonly=False,
    )
