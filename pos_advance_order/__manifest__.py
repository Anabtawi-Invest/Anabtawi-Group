{
    "name": "POS Advance Order",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Advance order screen in POS that captures extra fields and saves them on the POS order.",
    "author": "Softobia",
    "website": "https://softobia.com",
    "depends": ["point_of_sale"],
    "data": [
        "security/ir.model.access.csv",
    ],
    "assets": {
        "point_of_sale.assets": [
            "pos_advance_order_html/static/src/js/advance_order_button.js",
            "pos_advance_order_html/static/src/js/advance_order_screen.js",
            "pos_advance_order_html/static/src/js/order_export_patch.js",
            "pos_advance_order_html/static/src/xml/advance_order_templates.xml",
            "pos_advance_order_html/static/src/css/advance_order.css",
        ],
    },
    "license": "LGPL-3",
    "installable": True,
    "application": False
}
