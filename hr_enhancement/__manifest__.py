# -*- coding: utf-8 -*-
{
    "name": "HR Enhancement",
    "version": "19.0.1.0.0",
    "category": "Human Resources",
    "summary": "Time off dashboard: show hour balance with equivalent days",
    "depends": ["hr_holidays"],
    "data": [],
    "installable": True,
    "license": "LGPL-3",
    "assets": {
        "web.assets_backend": [
            "hr_enhancement/static/src/dashboard/time_off_card_patch.js",
            "hr_enhancement/static/src/dashboard/time_off_card_patch.xml",
        ],
    },
}
