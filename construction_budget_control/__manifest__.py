{
    "name": "Construction Budget & PO Approval Control",
    "version": "19.0.1.0.1",
    "category": "Construction",
    "summary": "Budget control and multi-level Purchase Order approval workflow for construction projects",
    "description": """
Construction Budget & PO Approval Control
==========================================

A standalone control layer for construction projects. It does NOT create any
accounting entries, vendor bills, or Purchase Orders in Odoo's Purchasing app -
it is purely a budget tracking and approval workflow tool that sits on top of
your existing accounting setup without touching it.

Features
--------
* Define a total budget per construction project.
* Users upload a Purchase Order (PDF/scan) together with a Bill of Materials
  (BOM) breakdown of quantities, unit prices and subtotals.
* Threshold-based, multi-level approval routing:
    - Accounting review (always required first)
    - General Manager review (required above a configurable amount)
    - Chairman review (required above a configurable amount)
* Hard budget block: a PO cannot be submitted if it would exceed the
  project's remaining budget (already-approved + currently pending POs are
  reserved against the budget).
* Full approval audit trail (who approved, when, rejection reasons) via
  chatter, tracking and dedicated approval fields.
* Export the Bill of Materials of a single PO, or of an entire project (all
  its POs), to a formatted Excel workbook.
""",
    "author": "Custom Development",
    "license": "LGPL-3",
    "depends": ["mail", "base", "base_setup"],
    "external_dependencies": {"python": ["xlsxwriter"]},
    "data": [
        "security/construction_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "views/construction_project_views.xml",
        "views/construction_po_views.xml",
        "views/res_config_settings_views.xml",
        "views/construction_menus.xml",
    ],
    "installable": True,
    "application": True,
}
