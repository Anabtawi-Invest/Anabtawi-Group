# Account Check Print

`account_check_print` is a configurable Odoo 19 Enterprise add-on for printing
vendor and miscellaneous outgoing business checks from `account.payment`.
It is not a payroll module.

## Highlights

- Independent layouts, paper sizes, languages, stock types, and number ranges per bank journal.
- OWL visual designer with background upload, drag, resize, live preview, and millimetre coordinates.
- QWeb PDF output with a dynamic custom `report.paperformat` for every layout.
- Atomic check-number reservation with a unique journal/number database constraint.
- Controlled first print, reason-required reprint, reason-required void, and immutable audit history.
- English and Arabic printing; amount words use Odoo's currency-aware language service.
- Multi-company access rules and explicit Accounting User/Manager separation.
- Layout snapshots ensure that a later design edit does not move fields on an already issued check.

## Compatibility

- Odoo 19 Enterprise
- Required Odoo applications: Accounting (`account`) and Web (`web`)
- License: LGPL-3

See [Installation](doc/INSTALLATION.md), [Configuration](doc/CONFIGURATION.md),
and [Developer Guide](doc/DEVELOPER.md).

