# -*- coding: utf-8 -*-
{
    "name": "Site Quality Control",
    "version": "19.0.1.0.0",
    "category": "Quality",
    "author": "Anabtawi",
    "summary": "Site-audit checklists (branches, departments, factories), scoring, grading, corrective actions, ranking & dashboard.",
    "description": """
Site Quality Control
====================
Periodic site-audit system for branches, departments, and factories:

* Site directory (master data)
* Configurable checklist templates (10 factors x 10 points = 100)
* Detailed per-question answers (pass/fail, 0-5, 0-10, comment, N/A, critical)
* Inspection workflow: Scheduled -> In Progress -> Submitted -> Reviewed ->
  Approved/Returned -> Corrective Actions -> Follow-up -> Closed
* Automatic scoring, configurable letter grading (A-F) and critical-failure override
* Corrective actions with evidence before/after and verification
* Site ranking, factor performance, priority sites, historical trends
* Executive dashboard and printable PDF inspection report
* Role-based security (Inspector / Site Manager / Quality Manager /
  Administrator / Management Viewer) with site & company scoping
* Scheduled automation (monthly inspections, reminders, escalations)

Self-contained. Optionally raises a standard Quality Alert on critical failures
when the Odoo Quality app is installed.
""",
    # Extends the standard Odoo Quality app: our Site Quality Control tab is
    # mounted under the Quality root menu and critical failures raise a
    # standard quality.alert. 'quality' pulls in stock/mail as needed.
    "depends": ["quality_control", "mail", "web", "base_setup"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "data/qc_grade_data.xml",
        "data/qc_checklist_template_data.xml",
        "data/qc_branch_data.xml",
        "data/qc_cron_data.xml",
        "reports/qc_inspection_report.xml",
        "views/qc_branch_views.xml",
        "views/qc_checklist_template_views.xml",
        "views/qc_grade_views.xml",
        "views/qc_inspection_views.xml",
        "views/qc_corrective_action_views.xml",
        "views/qc_report_views.xml",
        "views/qc_dashboard_views.xml",
        "views/qc_historical_views.xml",
        "views/res_config_settings_views.xml",
        "views/menu.xml",
    ],
    "installable": True,
    # Not a standalone app: it extends the Quality application's menu.
    "application": False,
    "license": "LGPL-3",
}
