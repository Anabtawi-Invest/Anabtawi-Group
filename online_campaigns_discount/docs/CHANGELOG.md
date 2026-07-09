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
