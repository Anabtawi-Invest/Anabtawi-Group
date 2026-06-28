# Installation Guide

1. Copy the `account_check_print` directory into an Odoo 19 custom add-ons path.
2. Add that directory's parent to `addons_path` in `odoo.conf`.
3. Restart Odoo, enable developer mode, and select **Apps → Update Apps List**.
4. Search for **Account Check Print** and install it.
5. Confirm that `wkhtmltopdf` is the Odoo-supported patched build. PDF printing uses Odoo's standard QWeb report service.

Command-line installation is also supported:

```bash
odoo-bin -d DATABASE -i account_check_print --stop-after-init
```

For upgrades, back up the database and filestore, deploy the new module files,
then run `-u account_check_print --stop-after-init`. Check numbers and audit
records are persistent database data and must not be manually renumbered.

