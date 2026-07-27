# -*- coding: utf-8 -*-
{
    'name': 'Contact Translatable Name',
    'version': '19.0.1.0.1',
    'category': 'Contacts',
    'summary': 'Make Contact/Partner name translatable in multiple languages (English, Arabic, etc.)',
    'description': """
Contact Translatable Name (Odoo 19)
====================================
Extends res.partner to make the name field translatable (translate=True).
Adds the language badge (EN/AR) next to the Contact Name so users can
enter names in multiple languages via the standard Odoo Translation Dialog.
    """,
    'author': 'Anabtawi Group',
    'website': 'https://www.anabtawisweets.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'contacts',
    ],
    'data': [
        'views/res_partner_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
