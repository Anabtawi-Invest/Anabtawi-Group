# __manifest__.py
{
    "name": "Ameen_Anabtawi_Packing List",
    "version": "19.0.1.0.0",
    "category": "Accounting",
    "summary": "Packing List PDF from Customer Invoices + product logistics fields",
    "depends": ["account", "sale", "stock", "product"],
    "data": [
        
        "views/package_type_menu.xml",
        "views/product_template_view.xml",
        "views/sale_order_view.xml",
        "report/packing_list_report.xml",
        "report/packing_list_template.xml",
    ],
    "installable": True,
    "application": False,
}
