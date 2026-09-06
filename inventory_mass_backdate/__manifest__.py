{
    'name': 'Inventory Mass Backdate',
    'version': '19.0.1.5.0',
    'category': 'Inventory/Inventory',
    'summary': 'Backdate completed stock transfers in bulk with a full audit trail',
    'description': """
Inventory Mass Backdate
========================

Lets authorized users change the completion date of stock transfers that
have already been validated (Done), in bulk, through a single wizard.

What it does
------------
* Select transfers with a search domain, or pick them from the Transfers
  list and run "Backdate Selected Transfers".
* Set a new date, type a reason (required).
* Optionally realign the dates of the linked, posted accounting entries
  that were generated for those stock moves (already-reconciled entries
  are left untouched).
* Every backdated transfer keeps an audit trail: the original completion
  date, who made the change, and why.

Only users in the "Inventory Backdate Manager" security group can see and
use this feature.
""",
    'author': 'Mohammed Alnsour',
    'website': '',
    'license': 'LGPL-3',
    'depends': ['stock', 'stock_account'],
    'external_dependencies': {'python': ['openpyxl', 'xlsxwriter']},
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'wizards/stock_backdate_wizard_views.xml',
        'wizards/stock_backdate_inventory_wizard_views.xml',
        'views/stock_picking_views.xml',
        'views/stock_quant_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
