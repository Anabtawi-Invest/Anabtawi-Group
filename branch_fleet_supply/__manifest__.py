{
    "name": "Branch Supply via Fleet (Manufacturing & Procurement)",
    "version": "19.0.1.0.0",
    "category": "Inventory",
    "summary": "Branch → Factory → Fleet → Branch supply with manufacturing and procurement automation",
    "description": """
Enterprise-grade Branch Supply workflow:
- Branch requests supply
- Manager approval
- Automatic inventory check
- Automatic Manufacturing Order creation if stock missing
- Automatic Purchase Request for raw materials
- Warehouse load → fleet dispatch → branch receive
""",
    "author": "Anabtawi Group",
    "website": "https://anabtawi.com",
    "depends": [
        "stock",
        "mrp",
        "purchase",
        "mail",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "views/branch_supply_menus.xml",
        "views/branch_supply_order_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
