{
    "name": "POS JoFotara Background Send",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Finish the POS payment when JoFotara is slow, then retry in the background",
    "author": "Anabtawi",
    "depends": ["l10n_jo_edi_pos"],
    "data": [
        "data/ir_cron.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_jofotara_background_send/static/src/app/receipt_screen_patch.js",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
