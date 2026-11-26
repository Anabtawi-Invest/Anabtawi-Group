{
    "name": "Stock Barcode Demand Quantity",
    "version": "19.0.1.3.4",
    "category": "Inventory/Inventory",
    "summary": "Branch demand and factory quantity on the same barcode transfer",
    "author": "Anabtawi",
    "depends": ["stock_barcode"],
    "data": [
        "security/security.xml",
        "views/stock_picking_type_views.xml",
        "views/stock_move_line_views.xml",
        "views/stock_picking_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "stock_barcode_demand_qty/static/src/**/*",
        ],
    },
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
