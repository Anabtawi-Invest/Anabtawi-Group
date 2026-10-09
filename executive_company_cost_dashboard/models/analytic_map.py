# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .classifier import classify_analytic


class CeoCostAnalyticMap(models.Model):
    """Tells the dashboard what each analytic account represents (a retail branch,
    a factory department, an admin department...). Branch P&L and department costs
    are built from the analytic distribution of the posted journal items."""

    _name = "ceo.cost.analytic.map"
    _description = "Dashboard Analytic Account Role"
    _rec_name = "analytic_id"
    _order = "kind, region, short_name"

    analytic_id = fields.Many2one(
        "account.analytic.account", string="Analytic Account", required=True, ondelete="cascade", index=True
    )
    kind = fields.Selection(
        [
            ("branch", "Retail Branch"),
            ("factory", "Factory / Supply Chain"),
            ("department", "Department"),
            ("other", "Ignore"),
        ],
        string="Role",
        required=True,
        default="branch",
    )
    short_name = fields.Char(string="Display Name", help="Name shown on the dashboard.")
    region = fields.Char(string="Region", help="Region / area number used to group branches.")
    pos_keywords = fields.Char(
        string="POS Name Keywords",
        help="Comma separated words. A Point of Sale whose name contains one of them is linked to "
        "this branch, so its sales are shown when the ledger has no analytic revenue for the branch.",
    )
    auto = fields.Boolean(string="Auto-classified", default=False)
    active = fields.Boolean(default=True)

    _analytic_unique = models.Constraint("UNIQUE(analytic_id)", "This analytic account is already classified.")

    @api.model
    def _classify(self, analytic):
        kind, short, region = classify_analytic(analytic.name)
        short = short or analytic.name
        keywords = ""
        if kind == "branch":
            # "فرع عين الباشا" -> "عين الباشا" so it matches the POS name as well
            keywords = short.replace("فرع", "").replace("كافيه", "").strip()
        return {"kind": kind, "short_name": short, "region": region, "pos_keywords": keywords}

    def write(self, vals):
        if {"kind", "short_name", "region", "pos_keywords"} & set(vals) and "auto" not in vals \
                and not self.env.context.get("ecd_scan"):
            vals = dict(vals, auto=False)
        return super().write(vals)
