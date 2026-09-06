{
    "name": "Inventory Backdate",
    "version": "19.0.1.1.0",
    "category": "Inventory/Inventory",
    "summary": "Backdate inventory adjustments and internal transfers with matching valuation",
    "description": """
Extends Odoo's Accounting Date on inventory adjustments so stock moves,
linked pickings, and journal entries all use the same historical date.

- Stock moves (and move lines) are dated with the Accounting Date
- Internal transfers can force an Effective Date on Validate
- Later movement values are replayed from the backdate so reports reconcile
- Optional Backdate Reason
- Automatic chatter audit on pickings and journal entries
- Backdated indicator on stock moves
    """,
    "author": "Anabtawi Group",
    "depends": ["stock_account"],
    "data": [
        "views/stock_quant_views.xml",
        "views/stock_move_views.xml",
        "views/stock_picking_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
