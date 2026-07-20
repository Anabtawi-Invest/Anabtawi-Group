# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class QcPersonnelHealth(models.Model):
    """Personnel fitness-to-work / hygiene declaration (GMP, ISO 22000
    §7.1.6 / prerequisite programs).

    A pre-shift or periodic screening record: symptomatic staff (illness,
    open wounds, skin infections) must be excluded or restricted from
    handling open food, per standard food-safety GMP requirements."""
    _name = "qc.personnel.health"
    _description = "Personnel Health / Hygiene Declaration (GMP)"
    _inherit = ["mail.thread"]
    _order = "date desc, id desc"

    employee_id = fields.Many2one(
        "hr.employee", string="Employee", required=True, tracking=True,
        index=True,
    )
    branch_id = fields.Many2one(
        "qc.branch", string="Site", required=True, tracking=True, index=True,
    )
    date = fields.Date(
        string="Date", required=True, default=fields.Date.context_today,
        tracking=True, index=True,
    )
    symptoms = fields.Selection(
        [
            ("none", "None reported"),
            ("gi_illness", "Gastrointestinal illness (vomiting/diarrhea)"),
            ("respiratory", "Respiratory infection / fever"),
            ("skin_wound", "Open wound, boil or skin infection"),
            ("jaundice", "Jaundice"),
            ("other", "Other"),
        ],
        string="Reported Symptoms", default="none", required=True,
        tracking=True,
    )
    symptom_notes = fields.Text(string="Details")
    fitness_status = fields.Selection(
        [
            ("fit", "Fit for Duty"),
            ("restricted", "Restricted (no open food handling)"),
            ("excluded", "Excluded from Work"),
        ],
        string="Fitness Status", compute="_compute_fitness_status",
        store=True, tracking=True,
    )
    action_taken = fields.Text(
        string="Action Taken",
        help="e.g. reassigned to non-food duties, sent home, cleared by "
             "medical certificate.",
    )
    cleared_return_date = fields.Date(
        string="Cleared to Return On",
        help="Set when a restricted/excluded employee is cleared to resume "
             "normal duties.",
    )
    reported_by_id = fields.Many2one(
        "res.users", string="Reported By",
        default=lambda self: self.env.user,
    )
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True,
        default=lambda self: self.env.company,
    )
    note = fields.Text(string="Notes")

    @api.depends("symptoms")
    def _compute_fitness_status(self):
        restricted = ("skin_wound",)
        excluded = ("gi_illness", "respiratory", "jaundice")
        for rec in self:
            if rec.symptoms in excluded:
                rec.fitness_status = "excluded"
            elif rec.symptoms in restricted:
                rec.fitness_status = "restricted"
            elif rec.symptoms == "other":
                # Ambiguous free-text case: default to restricted so a
                # supervisor reviews it rather than silently clearing it.
                rec.fitness_status = "restricted"
            else:
                rec.fitness_status = "fit"
