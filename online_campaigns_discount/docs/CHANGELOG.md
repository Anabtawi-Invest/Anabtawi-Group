## 19.0.5.1.0
- Added Talabat aggregator statement importer (.xlsx) on Aggregator Settlement: "Import Statement" button reads the statement file and fills Actual fields.
- Added "Download Template" button to generate a blank statement file with the expected columns.
- Added Statement Breakdown fields: TPro loyalty charges, TPro cost covered, sponsored deal fees, payment handling charges (+VAT), statement order count, cancelled-but-charged orders and their commission.
- Requires the `openpyxl` Python library (declared in external_dependencies).

## 19.0.5.0.3
- Fixed campaign accounting so discount recovery is posted to a dedicated configurable account instead of the normal Sales account.
- Reclassification from POS receivable to aggregator receivable is skipped when the aggregator payment method already posts directly to the aggregator receivable account.

# Changelog

## 19.0.5.0.0

- Rebased final release on the older stable POS-close behavior.
- Added robust POS branch/config filtering in frontend campaign logic.
- Kept aggregator sales and non-campaign aggregator sales reporting.
- Kept configurable before-tax/after-tax commission base.
- Kept settlement expected totals from campaign and non-campaign aggregator sales.
- Fixed SQL performance report syntax.
- Removed dependency on a campaign discount clearing account.
- Updated campaign cap documentation: per-order total cap allocated line by line.
- Added Odoo app icon under `static/description/icon.png`.
