# -*- coding: utf-8 -*-
{
    'name': 'Restrict Negative Stock by Location',               # ✔️ Module name
    'version': '1.0',                                            # ✔️ Version
    'author': 'Your Name',                                       # ✔️ Author
    'depends': ['stock'],                                        # ✔️ Depends on stock
    'category': 'Warehouse',                                     # ✔️ Category
    'summary': 'Restrict negative stock based on location checkbox',   # ✔️ Short summary
    'description': 'Adds checkbox on locations to restrict negative stock when checked.',  # ✔️ Description
    'data': [
        'views/stock_location_views.xml',                        # ✔️ View file included
    ],
    'installable': True,                                         # ✔️ Can be installed
    'application': False,                                        # ✔️ Not shown as main app
}
