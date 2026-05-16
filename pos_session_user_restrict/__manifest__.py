{
    'name': "POS Session User Restrict",

    'summary': "Restrict and control user access to Point of Sale sessions.",

    'description': """POS Session User Restrict is a functional enhancement for Odoo Point of Sale that allows administrators
                      to explicitly control which users are permitted to access and operate specific POS sessions.
                 """,

    'author': "Vishnu Sasikumar",
    'category': 'Point of Sale',
    'version': '1.0',
    'depends': ['base','point_of_sale'],

    'data': [
        'views/pos_config_views.xml'
    ],

    'images': ['static/description/banner.png'],

    'license': "LGPL-3",
    'installable': True,
    'application': True,
    'auto_install': False,
}

