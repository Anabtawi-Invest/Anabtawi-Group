# -*- coding: utf-8 -*-
{
    'name': 'POS Direct Network & USB Printer (Standalone)',
    'version': '19.0.1.0',
    'category': 'Point of Sale',
    'summary': 'Standalone Direct & Offline POS Receipt & Kitchen Printing (LAN & USB) for Multi-Branch Odoo 19',
    'description': """
        Direct, fast, and offline-capable POS receipt & kitchen printer integration.
        Supports LAN/IP ePOS thermal printers and USB printers without server-side database queues or polling lag.
    """,
    'author': 'Custom',
    'license': 'OPL-1',
    'depends': ['point_of_sale', 'pos_restaurant'],
    'data': [
        'security/ir.model.access.csv',
        'views/printer_printer_views.xml',
        'views/pos_printer_views.xml',
        'views/pos_config_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_direct_network_printer/static/src/**/*',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
