{
    "name": "POS Advance Order (POS Native)",
    "version": "19.0.1.1.0",
    "category": "Point of Sale",
    "summary": "Advance order workflow inside POS (native Owl UI) with scheduled datetime, type and customer details.",
    "author": "Softobia",
    "depends": ["point_of_sale"],
    "data": [
        "security/ir.model.access.csv",
        "views/pos_order_views.xml",
    ],
    "assets": {
        "point_of_sale.assets": [
            "pos_advance_order_new/static/src/js/advance_order_button.js",
            "pos_advance_order_new/static/src/js/advance_order_screen.js",
            "pos_advance_order_new/static/src/js/order_export_patch.js",
            "pos_advance_order_new/static/src/js/receipt_printing_patch.js",
            "pos_advance_order_new/static/src/xml/advance_order_templates.xml",
            "pos_advance_order_new/static/src/css/advance_order.css",
        ],
    },
    "license": "LGPL-3",
    "installable": True,
    "application": False
}
