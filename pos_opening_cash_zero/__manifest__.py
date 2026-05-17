# -*- coding: utf-8 -*-
{
    "name": "POS Opening Cash Zero",
    "summary": "Set opening cash to 0 when opening a POS session",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "assets": {
        "point_of_sale.assets_prod": [
            "pos_opening_cash_zero/static/src/app/**/*",
        ],
    },
    "installable": True,
    "application": False,
}
