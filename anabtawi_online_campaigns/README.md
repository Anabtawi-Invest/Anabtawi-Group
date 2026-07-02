# Online Campaigns Discount — Odoo 19 Enterprise

Portable campaign engine for POS orders received through Talabat, Careem,
MyThings, or any future aggregator. It provides calendar scheduling, dual
approval, automatic capped POS discounts, contribution accounting, commission
estimates, receipts, and reporting.

No company, currency, account, user, product, pricelist, or aggregator is
hardcoded. The same module can be installed unchanged in another Odoo 19
company.

## Version 2 analytics and settlement

Version 2 adds:

- line-level list, pivot, and graph analysis;
- a graphical campaign dashboard;
- signed profitability reporting that nets sales and refunds;
- gross sales, campaign cost, customer collections, estimated commission, and
  estimated net proceeds by aggregator, campaign, month, and POS session;
- aggregator settlement statements with attached source file;
- expected-versus-actual customer collections, contribution, commission, net
  settlement, amount variance, and variance percentage;
- finance-controlled confirmation and reconciliation, duplicate-period
  protection, bank statement/accounting entry links, and variance explanations.

## Workflow

1. Create an aggregator under **Online Campaigns > Configuration > Aggregators**.
   Set its default commission, company, contact, receivable account, company
   discount expense account, and commission expense account.
2. Create a campaign from the Campaigns list or Calendar. Enter start/end,
   aggregator, discount percentage, cap, POS configurations, POS pricelists,
   product scope, commission override, and aggregator/company contribution.
3. Submit the campaign. It remains inactive in POS while waiting.
4. A user in **Online Campaign E-commerce Manager** approves the operational
   terms. A user in **Online Campaign Finance Manager** approves the commercial
   and accounting setup. Approval order does not matter.
5. Only after both approvals does the campaign become `Approved`. Future
   approved campaigns are cached by POS but activate only at their scheduled
   start time. They stop automatically at the end time.
6. In POS, the order's active pricelist must be one selected on the campaign.
   The lowest priority matching campaign wins; stacking requires compatible
   same-aggregator campaigns with `Allow Stacking` enabled.

## Calculation

For an eligible line:

```text
gross = abs(unit price × quantity)
percentage discount = gross × campaign percentage
actual discount = percentage discount limited by per-unit/per-line/per-order cap
aggregator contribution = actual discount × aggregator contribution percentage
company contribution = actual discount - aggregator contribution
customer line payable = gross - actual discount
estimated commission = customer line payable × campaign commission percentage
```

Commission is also estimated for non-discounted products on the campaign
pricelist, because they are part of the same aggregator order. It is reported
but not posted automatically: actual aggregator commission normally arrives via
a settlement statement or vendor bill and may have taxes, adjustments, delivery
fees, or a different contractual base.

## POS and JoFotara safety

- Uses Odoo's native positive line discount percentage; it never adds a negative
  discount product line.
- Campaign discounts, caps, commissions, and contributions are stored as
  non-negative allowance amounts. Backend constraints reject negative values.
- Refund direction is carried by Odoo's standard refund quantity/credit-note
  document, not by a negative allowance.
- Currency formatting and rounding come from the company/POS currency. JOD is
  therefore shown with three decimals when JOD is configured correctly, without
  hardcoding JOD.
- Customer receipts show only aggregator campaign discount, net line, gross
  subtotal, campaign discount, and customer payable. Contributions and
  commission remain internal.

## Accounting

For non-invoiced POS orders, session closing adds balanced campaign lines:

- debit the aggregator's receivable account for its discount contribution;
- debit the aggregator's configured company discount expense account for the
  company contribution;
- credit affected product income accounts to restore the commercial gross sale.

Refunds reverse those entries based on standard line direction while all stored
allowance values remain positive. Invoiced POS orders remain under standard Odoo
invoice accounting. Estimated commission is reconciled separately from the
aggregator settlement/vendor bill using the configured commission expense
account.

### Settlement workflow

1. Finance creates an Aggregator Settlement for an aggregator, currency, and
   statement date range.
2. **Refresh Expected** reads paid/done POS campaign lines, including signed
   refunds, and calculates expected customer collections, contribution,
   commission, and net settlement.
3. Finance enters actual statement amounts, adjustments, statement reference,
   and optionally attaches the source statement.
4. **Confirm Statement** freezes the comparison period against overlapping
   confirmed/reconciled statements.
5. Finance links the bank statement line or accounting entry. A non-zero
   variance requires an explanation before **Mark Reconciled**.

## Installation

```bash
odoo-bin -d DATABASE -i anabtawi_online_campaigns --stop-after-init
```

Assign the approval groups in **Settings > Users**:

- Online Campaign E-commerce Manager
- Online Campaign Finance Manager

Restart/reload open POS browser tabs after installing or upgrading frontend
assets.

## Anabtawi deployment

Install the companion `anabtawi_online_campaigns` module after copying
`anabtawi_jo_pos_refund_buyer` from `D:\Anabtawi-Group-main.zip`. The companion
creates editable Talabat, Careem, and MyThings records and makes the Anabtawi
JoFotara fixes an explicit dependency. The portable engine itself does not
depend on the Anabtawi repository.

## Known operational boundaries

- Changing an approved campaign requires resetting it to draft and obtaining
  both approvals again.
- POS uses an offline-capable campaign snapshot. Date activation works offline;
  changes to products, scope, or approval state require normal POS data sync or
  reload to reach an already-open offline device.
- Database-authored custom receipt modules must add the exposed online campaign
  properties to their custom template because they replace Odoo's standard
  receipt tree.
- Commission posting is intentionally settlement-driven, not estimated-order-
  driven, to avoid double posting and tax errors.

## Tests

Tests cover caps, scopes, contribution split, commission, dual approval,
unapproved/expired filtering, backend totals, and non-negative refund allowances.

```bash
odoo-bin -d TEST_DATABASE -i anabtawi_online_campaigns \
  --test-enable --test-tags /anabtawi_online_campaigns --stop-after-init
```
