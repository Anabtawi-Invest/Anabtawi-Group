# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    "name": "User Record Activity Report",
    "version": "19.0.1.0.0",
    "category": "Tools",
    "summary": "Export users who created records in a date range",
    "depends": ["base"],
    "data": [
        "security/ir.model.access.csv",
        "wizard/user_record_activity_wizard_views.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
