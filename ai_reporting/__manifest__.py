# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    "name": "AI Reporting",
    "version": "19.0.1.0.0",
    "category": "Reporting",
    "summary": "Local-memory Ask AI optimization and confirmed advanced reports",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": ["base", "base_setup", "web", "mail"],
    "data": [
        "security/security_groups.xml",
        "security/ir.model.access.csv",
        "security/record_rules.xml",
        "data/ir_config_parameter.xml",
        "data/ir_cron.xml",
        "views/ai_reporting_memory_views.xml",
        "views/ai_reporting_request_views.xml",
        "views/ai_reporting_saved_report_views.xml",
        "wizard/ai_reporting_discovery_wizard_views.xml",
        "views/ai_reporting_settings_views.xml",
        "views/ai_reporting_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ai_reporting/static/src/js/report_builder.js",
            "ai_reporting/static/src/xml/report_builder.xml",
            "ai_reporting/static/src/scss/report_builder.scss",
        ],
    },
    "installable": True,
    "application": True,
}
