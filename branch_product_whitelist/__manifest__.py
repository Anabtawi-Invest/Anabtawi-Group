{
    "name": "Branch Product Whitelist for Internal Transfers-Ameen-Anabtawi",
    "version": "19.0.1.3.1",
    "category": "Inventory",
    "depends": ["stock", "product", "stock_picking_catalog", "stock_barcode"],
    "author":"Anabtawi",
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/menu.xml",
        "views/product_template_views.xml",
        "views/stock_move_line_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
