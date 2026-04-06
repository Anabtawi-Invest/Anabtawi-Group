{
    "name": "Ameen Packing List",
    "version": "19.0.1.0.0",
    "category": "Accounting",
    "author": "Ameen Arabiyat",
    "summary": "Two Packing List reports (with & without dates) + logistics fields + XLSX export (Action menu)",
    "depends": ["account", "sale", "stock", "product", "web"],
    "data": [
       

        "views/package_type_menu.xml",
        "views/product_template_view.xml",
        "views/sale_order_view.xml",

        "report/packing_list_report.xml",
        "report/packing_list_body.xml",
        "report/packing_list_template.xml",
        "report/packing_list_template_with_dates.xml",

        # NEW: Action menu XLSX export
        "views/packing_list_xlsx_actions.xml",
    ],
    "installable": True,
    "application": False,
}
