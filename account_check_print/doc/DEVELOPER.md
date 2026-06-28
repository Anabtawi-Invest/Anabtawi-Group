# Developer Guide

## Architecture

- `account.check.layout`: company-owned paper format, artwork, and field geometry.
- `account.journal`: enablement, selected layout, next number, language, and stock type.
- `account.payment`: check lifecycle and report helpers.
- `account.check.print.history`: immutable audit events.
- Transient void/reprint wizards collect mandatory reasons.
- `ir.actions.report.get_paperformat()` is extended only for this report so the active layout controls wkhtmltopdf page dimensions.
- The OWL client action reads and writes geometry through model methods; it does not bypass record rules.

Coordinates and dimensions are stored in millimetres. The QWeb template asks
`account.payment.check_field_style()` for each field's CSS; no check position is
hardcoded in XML. A first print snapshots geometry for deterministic reprints.

## Numbering transaction

`_reserve_check_number()` takes a PostgreSQL `FOR UPDATE` lock on the journal,
reads `next_check_number`, increments it, and writes the reserved value to the
payment in the same transaction. Rollbacks return the number automatically. A
database unique constraint on `(journal_id, check_number)` provides a second
line of defense.

## Security

Accounting Users have read access to layouts/history and can preview.
Accounting Managers can manage layouts and mutate check state. Python methods
repeat every permission check; hiding a button is never treated as security.
Company record rules use the active `company_ids` set.

## Tests

Run the module's post-install tests with:

```bash
odoo-bin -d TEST_DATABASE -i account_check_print \
  --test-enable --test-tags /account_check_print --stop-after-init
```

The suite covers numbering, duplicate print rejection, preview, reprint, void,
permissions, QWeb HTML rendering, and dynamic paper format selection. A real
printer calibration test remains an operational acceptance test because its
result depends on the printer driver and physical stock.

## Extension points

Override `check_payee_name()`, `check_amount_in_words()`, or
`_layout_snapshot_values()` for localization-specific requirements. Add new
designer fields by extending `_designer_field_names()`, supplying the four
geometry fields, updating the OWL label/sample maps, and rendering the new
field in QWeb.

