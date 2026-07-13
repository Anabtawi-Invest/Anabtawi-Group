{
    'name': 'POS Order Cost & Margin Report',
    'version': '19.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Adds Cost and Margin to POS order lines and a dedicated Cost & Margin report',
    'description': """
POS Order Cost & Margin Report
===============================

This small addon adds two fields to every Point of Sale order line:

* **Cost**  - the product's cost price (standard cost) multiplied by the quantity sold.
* **Margin** - Sales (untaxed) minus Cost.
* **Margin %** - Margin as a percentage of the untaxed sales amount.

It also adds a dedicated **POS Cost & Margin Report** menu (List / Pivot / Graph)
so you can analyse profitability of your Point of Sale orders, grouped and
filtered any way you like.

No changes are made to the POS front-end (the cash register screen) - this is
purely a back-office reporting addition.
""",
    'author': 'Custom Addon',
    'license': 'LGPL-3',
    'depends': ['point_of_sale'],
    'data': [
        'views/pos_order_line_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
