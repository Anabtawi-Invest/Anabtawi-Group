{
    "name": "Inventory Backdate",
    "version": "19.0.1.4.0",
    "category": "Inventory/Inventory",
    "summary": "Backdate inventory adjustments and internal transfers with matching valuation",
    "description": """
Extends Odoo's Accounting Date on inventory adjustments so stock moves,
linked pickings, and journal entries all use the same historical date.

- Stock moves (and move lines) are dated with the Accounting Date
- When Accounting Date is set, Counted Quantity is the count as of that date
- Later in/out moves are applied on top, so today's on-hand stays consistent
- Internal transfers can force an Effective Date on Validate
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
