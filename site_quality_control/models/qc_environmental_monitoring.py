# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class QcEnvironmentalMonitoring(models.Model):
    """Environmental monitoring sample (GMP / HACCP verification):
    surface swabs, water, air or product samples taken to verify that
    sanitation and process controls are effective. Failed results
    automatically raise a corrective action."""
    _name = "qc.environmental.monitoring"
    _description = "Environmental Monitoring Sample (GMP)"
    _inherit = ["mail.thread"]
    _order = "date desc, id desc"

    name = fields.Char(
        string="Reference", required=True, copy=False, readonly=True,
        default=lambda self: _("New"), index=True,
    )
    branch_id = fields.Many2one(
        "qc.branch", string="Site", required=True, tracking=True, index=True,
    )
    date = fields.Date(
        string="Sample Date", required=True, default=fields.Date.context_today,
        tracking=True, index=True,
    )
    sample_type = fields.Selection(
        [
            ("surface_swab", "Surface Swab"),
            ("water", "Water"),
            ("air", "Air"),
            ("product", "Product / Ingredient"),
            ("hand_swab", "Hand Swab"),
        ],
        string="Sample Type", default="surface_swab", required=True,
        tracking=True,
    )
    location = fields.Char(
        string="Sample Location",
        help="e.g. Prep table 2, Walk-in fridge door handle, Hand wash sink.",
    )
    ccp_id = fields.Many2one(
        "qc.ccp", string="Related CCP",
        help="Critical Control Point this sample verifies, if any.",
    )
    test_parameter = fields.Char(
        string="Test Parameter",
        help="e.g. ATP (RLU), Total Plate Count (CFU), Listeria, E.coli.",
    )
    measured_value = fields.Float(string="Measured Value")
    limit_value = fields.Float(
        string="Acceptance Limit",
        help="Value at or below which the sample passes.",
    )
    uom_name = fields.Char(string="Unit", help="e.g. RLU, CFU/cm2.")
    result = fields.Selection(
        [("pass", "Passed"), ("fail", "Failed")],
        string="Result", tracking=True,
    )
    lab_name = fields.Char(string="Lab / Analyst")
    certificate = fields.Binary(string="Lab Certificate", attachment=True)
    certificate_name = fields.Char(string="Certificate Filename")
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True,
        default=lambda self: self.env.company,
    )
    corrective_action_id = fields.Many2one(
        "qc.corrective.action", string="Corrective Action", readonly=True,
        copy=False,
    )
    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed")],
        string="Status", default="draft", required=True, tracking=True,
        copy=False,
    )
    note = fields.Text(string="Notes")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                seq = self.env["ir.sequence"].next_by_code(
                    "qc.environmental.monitoring")
                vals["name"] = seq or _("New")
        return super().create(vals_list)

    @api.onchange("measured_value", "limit_value")
    def _onchange_measured_value(self):
        # Always recompute so a legitimate zero-tolerance limit (e.g. 0
        # CFU for a pathogen test) is still evaluated correctly; the field
        # remains manually editable as the final source of truth.
        for rec in self:
            rec.result = (
                "pass" if rec.measured_value <= rec.limit_value else "fail")

    def action_set_result(self):
        """Confirm the result and raise a corrective action on failure."""
        for rec in self:
            if rec.state == "confirmed":
                raise UserError(_("This sample has already been confirmed."))
            if not rec.result:
                raise UserError(_(
                    "Set Pass or Fail before confirming this sample."))
            rec.state = "confirmed"
            if rec.result == "fail":
                rec._create_corrective_action()
        return True

    def _create_corrective_action(self):
        self.ensure_one()
        if self.corrective_action_id:
            return self.corrective_action_id
        action = self.env["qc.corrective.action"].create({
            "branch_id": self.branch_id.id,
            "environmental_monitoring_id": self.id,
            "problem": _(
                "Environmental monitoring failed — %(ref)s (%(date)s): "
                "%(type)s at %(location)s.") % {
                "ref": self.name,
                "date": self.date,
                "type": dict(self._fields["sample_type"].selection).get(
                    self.sample_type, self.sample_type),
                "location": self.location or "-",
            },
            "priority": "3",
            "responsible_id": self.branch_id.manager_id.id or False,
            "company_id": self.company_id.id,
        })
        self.corrective_action_id = action.id
        return action
