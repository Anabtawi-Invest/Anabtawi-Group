# -*- coding: utf-8 -*-
{
    'name': 'Anabtawi POS Branch Printer Mapping',
    'version': '19.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Connect and manage USB and LAN thermal receipt printers across 23 POS branches',
    'description': """
        Anabtawi POS Branch Printer Mapping
        ===================================
        Centralized module to assign USB and LAN network thermal printers across 23 branch POS configurations.
        Features:
        - Support for LAN (IP:Port) and USB printers per branch.
        - Pre-configured records for 23 branches (B01 through B23).
        - Strict security enforcement preventing branch cross-printing.
        - Automatic creation and synchronization of printer.printer and pos.printer records.
        - Seamless integration with cr_pos_network_printer_all_in_one for ESC/POS receipt printing.
        - Easily manage and assign printers to POS configurations for all 23 branches.
    """,
    'author': 'Anabtawi Group',
    'website': 'https://anabtawigroup.com',
    'license': 'OPL-1',
    'depends': [
        'base',
        'point_of_sale',
        'cr_all_in_one_direct_print',
        'cr_pos_network_printer_all_in_one',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/pos_branch_printer_data.xml',
        'views/pos_branch_printer_views.xml',
        'views/pos_config_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'anabtawi_pos_branch_printers/static/src/app/printers_override.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': True,
}
