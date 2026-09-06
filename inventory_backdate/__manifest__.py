{
    "name": "Inventory Backdate",
    "version": "19.0.1.0.0",
    "category": "Inventory/Inventory",
    "summary": "Backdate stock moves when an inventory adjustment uses Accounting Date",
    "description": """
Extends Odoo's Accounting Date on inventory adjustments so stock moves,
linked pickings, and journal entries all use the same historical date.

- Stock moves (and move lines) are dated with the Accounting Date
- Linked pickings get date_done updated
- Optional Backdate Reason on the inventory adjustment
- Automatic chatter audit on pickings and journal entries
- Backdated indicator on stock moves
    """,
    "author": "Anabtawi Group",
    "depends": ["stock_account"],
    "data": [
        "views/stock_quant_views.xml",
        "views/stock_move_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
