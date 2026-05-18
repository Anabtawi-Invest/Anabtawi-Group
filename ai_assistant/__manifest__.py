# -*- coding: utf-8 -*-
{
    "name": "AI Assistant",
    "summary": "Floating AI chat widget (OdooBot-style) for testing",
    "version": "19.0.1.0.0",
    "category": "Productivity",
    "license": "LGPL-3",
    "depends": ["base", "web", "mail"],
    "data": [
        "data/ai_assistant_data.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ai_assistant/static/src/scss/ai_assistant.scss",
            "ai_assistant/static/src/js/ai_assistant_panel.js",
            "ai_assistant/static/src/js/ai_assistant_hub.js",
            "ai_assistant/static/src/js/ai_assistant_service.js",
            "ai_assistant/static/src/xml/ai_assistant_panel.xml",
            "ai_assistant/static/src/xml/ai_assistant_hub.xml",
        ],
    },
    "installable": True,
    "application": False,
    "post_init_hook": "post_init_hook",
}
