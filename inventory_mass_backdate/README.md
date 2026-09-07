# Inventory Mass Backdate

An independent Odoo 19 module that lets authorized users change the
completion date of already-validated ("Done") stock transfers in bulk,
with a full audit trail. Built as a free, original implementation for
personal/company use — not derived from any commercial module's source
code.

## What it does

| Area | Model | Field(s) updated | When |
|------|-------|-------------------|------|
| Stock Transfer | `stock.picking` | `date_done` | Always |
| Stock Move | `stock.move` | `date` | Always |
| Stock Move Line | `stock.move.line` | `date` | Always |
| Accounting Entry | `account.move` | `date` | Only if "Recalculate Inventory Valuation" is checked; posted entries linked to the stock move; reconciled entries are skipped |

Audit fields added to the transfer: **Original Date Done**, **Backdated By**,
**Backdate Reason**.

## Install

1. Copy this `Inventory backdate advanced` folder into your Odoo addons path.
2. Restart Odoo, enable Developer Mode, go to Apps, click **Update Apps List**.
3. Search **Inventory Mass Backdate** and click **Install**.
4. Requires the `stock` and `stock_account` apps.

## Access

Only users in the **Inventory Backdate Manager** group (Settings → Users &
Companies → Groups) can see and use the wizard. The group implies Stock
Manager rights.

## Use

**Method 1 — Configuration menu:** Inventory → Configuration → Mass Backdate.
Set the new date, a reason (required), optionally check "Recalculate
Inventory Valuation", and set a filter domain, e.g.:

```
[('state', '=', 'done')]
[('state', '=', 'done'), ('picking_type_code', '=', 'outgoing')]
[('state', '=', 'done'), ('date_done', '>=', '2025-01-01')]
```

Click **Apply Mass Backdate**.

**Method 2 — from the Transfers list:** select one or more transfers,
open the **Action** (gear/list) menu, click **Backdate Selected Transfers**.
The wizard opens with the domain pre-filled to that selection.

Only transfers already in the **Done** state are ever touched. The domain
is parsed with `ast.literal_eval` (never `eval`) for safety.

## License

LGPL-3.
