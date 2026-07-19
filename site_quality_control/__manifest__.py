# -*- coding: utf-8 -*-
{
    "name": "International Site Quality Control",
    "version": "19.0.4.0.0",
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

Version 4 - International food-safety compliance layer
------------------------------------------------------
* Instrument register & calibration log; overdue instruments block submission (ISO 22000 8.7)
* CCP register (HACCP): hazards, critical limits, monitoring frequency
* Receiving inspections per delivery with Accept/Reject, lot & transfer links
* Approved supplier list; blocked suppliers cannot be accepted (ISO 7.1.6)
* Multiple daily monitoring rounds (morning/noon/evening)
* Locked completed records; admin-only unlock with permanent audit note
* Controlled SOP documents: versions, approval flow, review dates (ISO 7.5)
* Training & competency records with validity tracking (ISO 7.2)
* Allergen register linked to checklist questions (BRCGS 5.3)
* Management reviews with period KPIs and follow-up actions (ISO 9.3)
* Recall / mock-recall log with traceability and recovery metrics
""",
    # Extends the standard Odoo Quality app: our Site Quality Control tab is
    # mounted under the Quality root menu and critical failures raise a
    # standard quality.alert. 'quality' pulls in stock/mail as needed.
    "depends": ["quality_control", "mail", "web", "base_setup", "spreadsheet_dashboard", "stock", "hr"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "data/qc_grade_data.xml",
        "data/qc_checklist_template_data.xml",
        "data/qc_daily_checklist_data.xml",
        "data/qc_ccp_data.xml",
        "data/qc_receiving_template_data.xml",
        "data/qc_allergen_data.xml",
        "data/qc_branch_data.xml",
        "data/qc_cron_data.xml",
        "reports/qc_inspection_report.xml",
        "views/qc_branch_views.xml",
        "views/qc_checklist_template_views.xml",
        "views/qc_grade_views.xml",
        "views/qc_inspection_views.xml",
        "views/qc_daily_checklist_views.xml",
        "views/qc_receiving_views.xml",
        "views/qc_instrument_views.xml",
        "views/qc_ccp_views.xml",
        "views/qc_compliance_views.xml",
        "views/qc_corrective_action_views.xml",
        "views/qc_report_views.xml",
        "views/qc_dashboard_views.xml",
        "views/qc_historical_views.xml",
        "views/res_config_settings_views.xml",
        "data/qc_spreadsheet_dashboard_data.xml",
        "views/menu.xml",
    ],
    "installable": True,
    # Not a standalone app: it extends the Quality application's menu.
    "application": False,
    "license": "LGPL-3",
}
