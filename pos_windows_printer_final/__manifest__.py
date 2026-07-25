# -*- coding: utf-8 -*-
{
    'name': 'Windows Printer Agent & POS Direct Print Solution (Final)',
    'version': '19.0.1.1.0',
    'category': 'Point of Sale',
    'summary': 'Unified Direct Printing Solution for Odoo Reports & POS (Windows Agent, LAN & USB)',
    'description': """
        Enterprise Direct & Offline Printing Solution for Odoo 19.
        Features:
        - Full Windows Printer Agent integration (Auto-syncs local Windows printers)
        - Direct Backend Report Printing (Invoices, Pickings, Purchase Orders, Labels)
        - High-speed POS Receipt & Kitchen Order printing (LAN, USB, Bluetooth)
        - 100% Offline Session Support with zero database queue lag
        - Secure Token Authentication per Windows Host/Branch
    """,
    'author': 'Custom',
    'license': 'OPL-1',
    'depends': ['base', 'mail', 'point_of_sale', 'pos_restaurant'],
    'external_dependencies': {
        'python': ['PIL'],
    },
    'data': [
        'security/ir.model.access.csv',
        'views/print_engine_client_views.xml',
        'views/printer_printer_views.xml',
        'views/print_job_views.xml',
        'views/ir_actions_report_views.xml',
        'views/report_print_wizard_views.xml',
        'views/pos_printer_views.xml',
        'views/pos_config_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_windows_printer_final/static/src/**/*',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
