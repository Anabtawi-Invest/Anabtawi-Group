{
    "name": "Stock Next Transfer Print",
    "version": "19.0.1.1.0",
    "category": "Inventory/Inventory",
    "summary": "Print the Picking Operations report of the next transfer",
    "author": "Anabtawi",
    "depends": ["stock"],
    "data": [
        "security/ir.model.access.csv",
        "views/stock_picking_views.xml",
        "wizard/print_next_transfer_views.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
