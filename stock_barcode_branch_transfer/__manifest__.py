{
    "name": "Stock Barcode Branch Transfer",
    "version": "19.0.1.0.3",
    "category": "Inventory/Inventory",
    "summary": "Override and lock barcode transfer locations from the first scanned source and destination",
    "author": "Anabtawi",
    "depends": ["stock_barcode"],
    "data": [
        "views/stock_picking_type_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "stock_barcode_branch_transfer/static/src/**/*",
        ],
    },
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
