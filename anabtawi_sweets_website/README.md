# Anabtawi Sweets Website Theme

Production-oriented Odoo 19 Website theme based on the public Anabtawi Sweets website.

## Included pages

- Home (`/`), implemented by safely inheriting Odoo's existing homepage view
- About (`/aboutus`)
- Branches (`/branches`)
- Product catalog (`/our-catalog`)
- Contact (`/contactus`), implemented with Odoo's native website form endpoint

## Technical scope

- Requires only `website`
- Contains no custom controllers, models, security rules, cron jobs, or database tables
- Uses Odoo 19 Website/QWeb XML, Bootstrap 5 utilities, frontend SCSS assets, and Website Builder snippets
- Packages the source website's required images locally

See `INSTALLATION.md`, `MIGRATION_REPORT.md`, and `COMPATIBILITY_REPORT.md` for deployment and audit details.
