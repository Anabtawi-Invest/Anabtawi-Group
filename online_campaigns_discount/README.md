# Online Campaigns Discount — Odoo 19 Enterprise Stable 

Enterprise POS aggregator management for Anabtawi Group and reusable Odoo 19 deployments.
The module manages aggregator campaigns, capped discounts, contribution splits,
commission estimates, accounting entries, profitability reports, and settlement tracking.

## Current release

**Version:** 19.0.5.0.0

## Key features

- Aggregator setup for Talabat, Careem, MyThings, and future platforms.
- POS payment method mapping per aggregator.
- Commission base configurable per aggregator: before tax or after tax.
- Campaign approval workflow: draft, waiting for approval, approved, rejected, cancelled.
- E-commerce approval and finance approval before campaign activation.
- Branch restriction by selected POS configurations.
- Pricelist restriction by selected POS pricelists.
- Product eligibility by all products, selected products, or selected categories.
- Campaign contribution split between company and aggregator.
- Campaign profitability reports and dashboards.
- Aggregator sales reports including non-campaign aggregator sales.
- Settlement expected totals for customer collections, contribution, commission, net settlement, and variance.
- Application icon included under `static/description/icon.png`.

## Discount cap rule used by Anabtawi

For Talabat-style campaigns, use **Per Order** cap.

The cap is one total allowance for the whole order and is allocated line by line:

```text
remaining_cap = campaign cap
for each eligible line in order sequence:
    calculated_discount = line gross × discount percentage
    applied_discount = min(calculated_discount, remaining_cap)
    remaining_cap = remaining_cap - applied_discount
    if remaining_cap = 0:
        later eligible lines receive zero discount
```

Non-eligible products do not consume the cap and do not affect discounted items.

## Tax and commission rules

- Sales and VAT remain posted by standard Odoo POS.
- The module must not duplicate revenue.
- The module must not duplicate VAT.
- VAT is calculated after the customer discount.
- Campaign contributions are calculated on tax-exclusive discount value.
- Commission can be calculated before tax or after tax based on aggregator configuration.

## Accounting rules

For campaign orders, the POS session accounting adds only the campaign/commission adjustments:

```text
Dr Aggregator Receivable          aggregator contribution
Dr Company Discount Expense       company contribution
Cr POS Receivable                 total campaign discount

Dr Commission Expense             estimated commission
Cr Aggregator Receivable          estimated commission deduction
```

The module does not use a permanent campaign clearing account.

## Settlement workflow

Finance creates an Aggregator Settlement per aggregator and statement period.
The settlement reads expected values from the performance report:

- customer collections,
- aggregator contribution,
- estimated commission,
- expected net settlement,
- actual statement values,
- variance and variance reason.

A settlement can be marked reconciled after linking a bank statement line or accounting entry.

## POS closing safety

This release keeps the POS closing logic aligned with the older stable module flow.
It does not write or mutate POS order lines during the POS session closing process.
This is intended to preserve Anabtawi's fast cashier close behavior.

After updating JavaScript or campaign logic, clear browser/POS cache and start a new POS session.

## Release checklist

Before production deployment, validate on staging:

1. Normal POS sale without aggregator.
2. Aggregator sale without campaign.
3. Aggregator sale with campaign.
4. Campaign applies only to selected POS branch.
5. Campaign applies only to selected pricelist.
6. Per-order cap line allocation works.
7. POS closes normally.
8. Accounting journal has no duplicated revenue or VAT.
9. Aggregator Sales report shows campaign and non-campaign sales.
10. Settlement expected totals are correct.
