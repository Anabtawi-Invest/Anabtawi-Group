# Installation

## Clean Odoo 19 database

1. Install the **Website** application.
2. Copy the `anabtawi_sweets_website` directory into a directory listed in Odoo's `addons_path`.
3. Restart Odoo.
4. Enable developer mode, open **Apps**, and select **Update Apps List**.
5. Search for **Anabtawi Sweets Website Theme** and install it. The module is intentionally visible in the Apps dashboard.
6. Open the website and verify `/`, `/aboutus`, `/branches`, `/our-catalog`, and `/contactus`.
7. In Website settings, set the company/website logo, domain, language choices, email address, and outgoing mail server for the target database.
8. Clear browser assets or restart Odoo with asset regeneration if an older copy of the module was installed previously.

## Command-line update

```text
odoo-bin -d DATABASE_NAME -i anabtawi_sweets_website --stop-after-init
```

For a later code update:

```text
odoo-bin -d DATABASE_NAME -u anabtawi_sweets_website --stop-after-init
```

The three custom `website.page` records and menu records use `noupdate="1"` so Website Builder edits are preserved on module upgrades.
