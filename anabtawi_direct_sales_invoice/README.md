# Anabtawi Direct Sales Invoice

Production-oriented Odoo 19 Enterprise workflow for direct customer invoices that
must be approved, reserved, prepared, and released by a warehouse while retaining
standard Odoo stock, accounting, tax, payment, return, and credit-note behavior.

## Module identity

| Item | Value |
|---|---|
| Display name | Anabtawi Direct Sales Invoice |
| Technical name | `anabtawi_direct_sales_invoice` |
| Version | `19.0.1.0.0` |
| License | LGPL-3 |
| Category | Sales / Inventory / Accounting |

Dependencies are exactly `base`, `mail`, `sale_management`, `account`, `stock`,
`product`, and `contacts`.

## Installation

1. Copy the `anabtawi_direct_sales_invoice` directory into an Odoo 19 add-ons
   path, or upload the versioned ZIP to the Odoo.sh custom add-ons repository.
2. Restart Odoo.
3. Enable developer mode and select **Apps → Update Apps List**.
4. Search for **Anabtawi Direct Sales Invoice** and install it.
5. Assign Direct Sales roles to users before opening the application.

Command-line installation example:

```bash
odoo-bin -d DATABASE \
  --addons-path=/path/to/odoo/addons,/path/to/custom/addons \
  -i anabtawi_direct_sales_invoice \
  --stop-after-init
```

Upgrade after deploying a newer module revision:

```bash
odoo-bin -d DATABASE \
  --addons-path=/path/to/odoo/addons,/path/to/custom/addons \
  -u anabtawi_direct_sales_invoice \
  --stop-after-init
```

## Initial configuration

Open **Direct Sales → Configuration → Settings** and configure the company:

- Enable Direct Sales Invoice.
- Choose invoice creation at warehouse approval or goods release.
- Choose whether the invoice is posted automatically after release.
- Choose the default direct-delivery or two-step dispatch flow.
- Configure the cash-release policy.
- Enable partial approval and/or multi-warehouse fulfillment when required.
- Select an optional sales journal, fallback payment term, and default dispatch
  location.
- Choose whether prices appear on the internal warehouse preparation sheet.
- Choose whether manual price overrides require manager approval.

Then open **Direct Sales → Configuration → Warehouses**:

1. Open each warehouse that participates in the workflow.
2. Select **Initialize Direct Sales Setup**. The operation is idempotent.
3. Confirm the warehouse-specific **Sales Dispatch** internal location and
   **Direct Sales Preparation** operation type.
4. Assign permitted Direct Sales users and at least one warehouse approver.
5. Select the warehouse stock flow.

The initializer reuses an applicable configured location/operation type and does
not create duplicates.

Assign one or more roles under the Direct Sales user privileges:

- Direct Invoice User
- Direct Invoice Sales Manager
- Allow Direct Invoice Price Override
- Direct Invoice Warehouse User
- Direct Invoice Warehouse Manager
- Direct Invoice Accounting User
- Direct Invoice Administrator

Standard Sales, Inventory, and Accounting groups are implied where the role needs
their standard Odoo capabilities.

## User workflow

1. A salesperson creates a Direct Invoice.
2. Selecting the customer loads and stores the customer's standard Odoo
   pricelist, currency, payment terms, and fiscal position.
3. Selecting an enabled pickup warehouse sets the warehouse source, dispatch
   location, and configured stock-flow snapshot.
4. Product prices are calculated through the Odoo 19 pricelist API. Any manual
   price requires the override group and a reason; submission can require Sales
   Manager approval.
5. **Submit to Warehouse** freezes commercial terms, creates one approval
   activity per approver, and records an immutable audit event.
6. A Warehouse Manager approves all stock, approves a partial quantity, or
   rejects the request.
7. Approval creates standard `stock.picking` and `stock.move` records:
   - Direct delivery: warehouse stock → customer.
   - Two-step dispatch: warehouse stock → Sales Dispatch → customer.
8. Warehouse users validate standard transfers, including standard lot/serial
   handling and removal strategies, then mark the document ready.
9. **Confirm Goods Release** validates the customer release picking, records the
   receiver, released quantities, lots, user, and timestamp, then creates/posts
   the standard customer invoice according to company policy.
10. Accounting uses standard Odoo posting, payment registration, reconciliation,
    credit-note, and reporting workflows.

Normal states are:

```text
Draft → Waiting Warehouse Approval → Warehouse Approved
      → Ready for Pickup → Goods Released → Completed
```

Alternative outcomes are Partially Approved, Rejected, and Cancelled.

## Stock and traceability behavior

- Availability uses standard product stock fields in the selected location
  hierarchy and company context; no direct SQL or custom stock ledger is used.
- Approval creates reservations with standard pickings and moves.
- Released quantities come from completed standard stock moves.
- Released lot/serial records are linked back to each direct invoice line.
- If the standard stock expiration feature is installed, expiration data remains
  available through those linked `stock.lot` records.
- Standard backorders retain the Direct Sales document, invoice, warehouse, and
  stage links.
- Standard return pickings are created by `stock.return.picking` and retain the
  Direct Sales document and line links.
- Validated moves are never deleted or rewritten by this module.

In multi-warehouse mode, allocation quantities must total the requested line
quantity. Approval validates free stock and user assignment for every allocated
source. Each warehouse/source receives its own picking while the customer
receives one standard invoice.

## Accounting and pricing behavior

- Customer invoices are ordinary `account.move` records with
  `move_type = 'out_invoice'`.
- Customer, invoice address, salesperson, sales team, date, payment term,
  currency, fiscal position, taxes, product/UoM, approved or released quantity,
  price, discount, analytic distribution, and customer note are copied.
- Invoice creation and stock creation are idempotent and reuse existing linked
  records.
- The customer pricelist and pickup warehouse are stored as internal invoice
  fields.
- This module does not inherit or change the standard customer invoice QWeb
  document, so the pricelist and override audit do not appear on the customer PDF.
- Cash sales can require a posted, fully paid and reconciled invoice before
  release. Credit sales continue to use standard payment terms and residual
  balances.
- Posted invoice values are not silently synchronized from the Direct Sales
  document.

## Cancellation and reversal

- Before release, authorized cancellation cancels open standard pickings and
  frees reservations.
- A document with a completed transfer cannot be directly cancelled.
- After release, use **Create Return** and the standard stock return wizard.
- For a posted invoice, use **Create Credit Note** and the standard account move
  reversal wizard.
- Approval records remain immutable.

## Reports

The module provides list, pivot, and graph analysis for warehouse, customer,
pricelist, salesperson, product movement, cash/credit sales, outstanding amounts,
partial/rejected requests, and manual price overrides.

Internal QWeb documents:

- Warehouse Preparation Sheet
- Goods Release Document
- Internal Commercial Audit

The commercial audit report is restricted to Direct Invoice Sales Managers and
standard Accounting Managers. Warehouse prices appear only when enabled in
company settings.

## Technical architecture

New persistent models:

- `direct.sales.invoice`
- `direct.sales.invoice.line`
- `direct.sales.invoice.allocation`
- `direct.sales.invoice.approval`

New transient workflow models:

- `direct.sales.warehouse.approval.wizard`
- `direct.sales.partial.approval.wizard`
- `direct.sales.partial.approval.wizard.line`
- `direct.sales.rejection.wizard`
- `direct.sales.goods.release.wizard`

Inherited standard models:

- `res.company`
- `res.config.settings`
- `res.users`
- `stock.warehouse`
- `stock.picking`
- `stock.move`
- `stock.move.line`
- `stock.return.picking`
- `stock.return.picking.line`
- `account.move`
- `account.move.line`

Major actions perform access checks on the server, validate current state, check
warehouse assignment, and use linked-record searches before creating stock or
accounting records. Workflow and audit fields cannot be forged through generic
RPC writes.

The optional local Anabtawi warehouse restriction fields
`restrict_ware_house` and `allowed_ware_house_ids` are honored dynamically when
present, without adding a hard dependency. The module creates stock operations
through standard Odoo models, so existing stock quantity and negative-location
guards continue to execute normally.

## Automated tests

The suite covers:

- customer, quantity, date-validity, and currency pricelists;
- preservation and non-printing of the stored pricelist;
- enabled/permitted warehouses and location-scoped availability;
- full, partial, rejected, duplicate, and multi-warehouse approval;
- direct delivery, two-step dispatch, lot traceability, back links, and returns;
- invoice field/tax/term copying, creation policies, posting, and idempotency;
- immediate standard payment registration, credit residuals, maturity dates, and
  payment-before-release behavior;
- price override permissions, reasons, approval audit, and submission control;
- role actions, record rules, unauthorized warehouse isolation, and forged RPC
  write prevention.

Run all module tests on an Odoo 19 test database:

```bash
odoo-bin -d DSI_TEST \
  --addons-path=/path/to/odoo/addons,/path/to/custom/addons \
  -i anabtawi_direct_sales_invoice \
  --test-enable \
  --test-tags /anabtawi_direct_sales_invoice \
  --stop-after-init
```

Tests are tagged `post_install` and `-at_install`.

## Assumptions

- Odoo 19 Enterprise and the declared dependencies are already available.
- Customer pricelists use the standard
  `res.partner.property_product_pricelist` property.
- Products used by this workflow are saleable and storable.
- Each participating warehouse has assigned permitted users and approvers.
- A single manager approving a multi-warehouse document must be assigned to all
  source warehouses; every source warehouse still receives its own activities.
- Full cash clearance means Odoo reports the invoice as **Paid** after standard
  registration and reconciliation; **In Payment** is not treated as reconciled.
- Fiscal localization, tax accounts, journals, stock valuation, removal
  strategies, lots, expiry rules, payments, and reconciliation remain standard
  Odoo configuration responsibilities.

No Odoo core files are modified.
