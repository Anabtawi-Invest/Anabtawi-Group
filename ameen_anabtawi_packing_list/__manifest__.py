{
    "name": "Ameen Packing List",
    "version": "19.0.1.0.0",
    "category": "Accounting",
    "summary": "Packing List PDF + XLSX export from Action menu",
    "depends": ["account", "sale", "stock", "product", "web"],
    "data": [
        "security/ir.model.access.csv",

        "views/package_type_menu.xml",
        "views/product_template_view.xml",
        "views/sale_order_view.xml",

        "report/packing_list_report.xml",
        "report/packing_list_body.xml",
        "report/packing_list_template.xml",
        "report/packing_list_template_with_dates.xml",

        # NEW: Action menu XLSX
        "views/packing_list_xlsx_actions.xml",
    ],
    "installable": True,
    "application": False,
}
