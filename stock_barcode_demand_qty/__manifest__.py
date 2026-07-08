{
    "name": "Stock Barcode Demand Quantity",
    "version": "19.0.1.1.0",
    "category": "Inventory/Inventory",
    "summary": "Add a demand quantity field to the barcode transfer product form",
    "author": "Anabtawi",
    "depends": ["stock_barcode"],
    "data": [
        "views/stock_picking_type_views.xml",
        "views/stock_move_line_views.xml",
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
