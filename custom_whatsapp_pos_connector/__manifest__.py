{
    "name": "Custom WhatsApp POS Connector",
    "version": "19.0.1.0.0",
    "summary": "Receive WhatsApp guided orders and push to POS",
    "category": "Point of Sale",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": ["base", "point_of_sale", "contacts", "web"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "views/res_config_settings_views.xml",
        "views/whatsapp_pos_order_views.xml",
        "views/menu_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "custom_whatsapp_pos_connector/static/src/js/whatsapp_pos_popup.js",
            "custom_whatsapp_pos_connector/static/src/js/whatsapp_pos_listener.js",
            "custom_whatsapp_pos_connector/static/src/xml/whatsapp_pos_popup.xml",
        ],
    },
    "installable": True,
    "application": False,
}
