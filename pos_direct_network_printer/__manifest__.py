# -*- coding: utf-8 -*-
{
    'name': 'POS Multi-Branch IoT Printing',
    'version': '19.0.2.0',
    'category': 'Point of Sale',
    'summary': 'Install the official Odoo IoT printing stack for multi-branch POS',
    'description': """
        Enables Odoo's official POS IoT integration for silent receipt,
        cash-drawer, and preparation printing. Printers are connected and
        assigned through Odoo IoT and Point of Sale configuration.
    """,
    'author': 'Custom',
    'license': 'OPL-1',
    'depends': ['point_of_sale', 'pos_restaurant', 'pos_iot'],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
