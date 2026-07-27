# Contact Translatable Name (`contact_name`)

Odoo 19 Custom Addon to enable multi-language translatable names for Contacts (`res.partner`).

## Features
- Extends `res.partner` model to set `translate=True` on the `name` field.
- Automatically enables the Odoo Language Badge (`EN`, `AR`, etc.) beside the contact name input on Form Views.
- Allows entering names in Arabic, English, French, and any other installed language via Odoo's native Translation Dialog popup (`Translate: name`).

## Structure
```
contact_name/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   └── res_partner.py
├── views/
│   └── res_partner_views.xml
└── README.md
```

## Compatibility
- Odoo 19.0+
- License: LGPL-3
