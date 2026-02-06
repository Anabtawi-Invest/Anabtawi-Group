{
    "name": "Branch Supply via Fleet",
    "version": "19.0.1.0.0",
    "category": "Inventory",
    "summary": "Branch supply workflow with manufacturing and procurement",
    "description": "Branch supply workflow with inventory check, manufacturing and procurement automation.",
    "author": "Anabtawi Group",
    "website": "https://anabtawi.com",
    "depends": [
        "stock",
        "mrp",
        "purchase",
        "mail"
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "views/branch_supply_menus.xml",
        "views/branch_supply_order_views.xml"
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3"
}
