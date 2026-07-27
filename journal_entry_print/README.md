# Journal Entry PDF

Small Odoo 19 add-on that adds **Journal Entry PDF** to the existing
`account.move` Print menu.

The report:

- accepts only regular journal entries (`move_type == "entry"`);
- prints every `line_ids` record without filtering, merging, or summarizing;
- supports one or multiple selected journal entries;
- retains Odoo's existing reports and accounting behavior unchanged;
- uses Odoo's external report layout, company currency, and monetary formatting;
- lays out mixed Arabic and English journal-item text with a Unicode-capable font.

## Installation

Place `journal_entry_print` in an Odoo add-ons path, update the Apps list, and
install **Journal Entry PDF**.
