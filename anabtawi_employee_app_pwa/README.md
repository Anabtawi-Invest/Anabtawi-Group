# Anabtawi Employee App PWA

Odoo 19 / Odoo.sh module exposing the Employee App PWA at `/employee-portal`.

Version: 19.0.1.1.0

Important behavior:
- The app is named Employee App, not HR App.
- PWA starts at `/employee-portal` and is scoped to `/employee-portal`.
- The install card is hidden when the app is already running as a standalone PWA.
- The Employee App uses `/anabtawi/mobile/*` APIs only.
- Device restriction is enforced by the API only and never affects standard Odoo `/odoo` login.
