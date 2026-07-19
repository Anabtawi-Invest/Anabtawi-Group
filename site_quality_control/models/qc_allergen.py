# -*- coding: utf-8 -*-
from odoo import fields, models


class QcAllergen(models.Model):
    """Allergen register (BRCGS §5.3).

    Master list of allergens handled on sites. Checklist questions can be
    tagged with the allergens they control, making allergen monitoring
    traceable in audits and daily checklists."""
    _name = "qc.allergen"
    _description = "Allergen"
    _order = "sequence, name"

    name = fields.Char(string="Allergen", required=True, translate=True)
    code = fields.Char(string="Code")
    sequence = fields.Integer(default=10)
    description = fields.Text(
        string="Handling Notes", translate=True,
        help="Where this allergen is present on site and how cross-contact "
             "is controlled (segregation, cleaning, labelling).",
    )
    active = fields.Boolean(default=True)
    question_ids = fields.Many2many(
        "qc.question.template", "qc_question_allergen_rel",
        "allergen_id", "question_id",
        string="Linked Questions", readonly=True,
    )

    _sql_constraints = [
        ("name_uniq", "unique(name)", "This allergen already exists."),
    ]
