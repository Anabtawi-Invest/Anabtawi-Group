# -*- coding: utf-8 -*-
{
    'name': 'Anabtawi POS Branch Printers',
    'version': '19.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Unified standalone LAN and USB thermal receipt printing module for 23 POS branches',
    'description': """
        Anabtawi POS Branch Printers
        ============================
        A single, zero-dependency, self-contained Odoo 19 module to manage LAN (IP/Port) and USB thermal receipt printers across 23 POS branches.
        
        Key Features:
        - Built-in native ESC/POS thermal raster engine & RAW socket handler (Port 9100).
        - Direct cash drawer pulse trigger (ESC p 0 25 250).
        - Strict branch isolation preventing cross-branch printing.
        - Pre-configured setup for 23 branches (B01 to B23).
        - Zero 3rd-party module dependencies.
    """,
    'author': 'Anabtawi Group',
    'website': 'https://anabtawigroup.com',
    'license': 'OPL-1',
    'depends': [
        'base',
        'point_of_sale',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/pos_branch_printer_views.xml',
        'views/pos_config_views.xml',
        'views/menu_views.xml',
        'data/pos_branch_printer_data.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'anabtawi_pos_branch_printers/static/src/app/branch_printer.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': True,
}
