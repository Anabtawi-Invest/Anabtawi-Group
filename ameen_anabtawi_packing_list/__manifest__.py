{
    "name": "Ameen Packing List",
    "version": "19.0.1.0.0",
    "category": "Accounting",
    "summary": "Two Packing List reports (with & without dates) + logistics fields",
    "depends": ["account", "sale", "stock", "product"],
    "data": [
        # Security (needed for packing.package.type create/save)
        "security/ir.model.access.csv",

        # Views
        "views/package_type_menu.xml",
        "views/product_template_view.xml",
        "views/sale_order_view.xml",

        # Reports (2 actions)
        "report/packing_list_report.xml",

        # QWeb templates (Body must be loaded first)
        "report/packing_list_body.xml",
        "report/packing_list_template.xml",
        "report/packing_list_template_with_dates.xml",
    ],
    "installable": True,
    "application": False,
}
