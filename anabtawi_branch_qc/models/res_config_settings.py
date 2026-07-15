# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    qc_create_quality_alert = fields.Boolean(
        string="Create Quality Alert on Critical Failure",
        config_parameter="anabtawi_branch_qc.create_quality_alert",
        help="When enabled and the Odoo Quality app is installed, a Quality "
             "Alert is created automatically whenever an inspection has a "
             "critical failure.",
    )
    qc_default_passing_score = fields.Float(
        string="Default Minimum Passing Score",
        config_parameter="anabtawi_branch_qc.default_passing_score",
        default=60.0,
    )
