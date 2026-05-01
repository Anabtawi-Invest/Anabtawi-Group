# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "POS Predefined Discounts",
    "version": "1.0.0",
    "category": "Sales/Point of Sale",
    "summary": "Select predefined discounts from POS instead of typing a number",
    "depends": ["point_of_sale", "pos_discount", "employee_request", "pos_advance_order"],
    "data": [
        "security/ir.model.access.csv",
        "views/pos_predefined_discount_views.xml",
        "views/pos_predefined_discount_menu.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_predefined_discounts/static/src/app/models/pos_predefined_discount.js",
            "pos_predefined_discounts/static/src/app/screens/product_screen/predefined_discount_auth_popup.js",
            "pos_predefined_discounts/static/src/app/screens/product_screen/predefined_discount_auth_popup.xml",
            "pos_predefined_discounts/static/src/app/screens/product_screen/control_buttons_predefined_discount.js",
        ],
    },
    "installable": True,
    "license": "LGPL-3",
}

