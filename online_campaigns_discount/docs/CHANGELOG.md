## 19.0.5.5.1
- Fixed module upgrade failure: `models.UniqueIndex(...)` on the aggregator model (pre-existing code) raised at import time on this Odoo build, silently taking down every model in the addon (online.discount.campaign, online.campaign.aggregator, online.campaign.settlement, online.campaign.performance.report all failed to register - "Missing model" errors in log). Replaced with the standard `_sql_constraints` syntax, which works on every Odoo version.

## 19.0.5.5.0
- Moved the POS payment-time aggregator order ID popup out of this module and into `pos_pricelist_id` (already deployed), which now depends on this module and reads the aggregator config (payment methods, require_order_ref, order_ref_digit_length) from here. Avoids running two competing popups if both modules are installed.
- This module still owns: `online_aggregator_order_ref` field (loaded to POS frontend, validated server-side), and the aggregator's `require_order_ref`/`order_ref_digit_length` config fields.

## 19.0.5.4.0
- Added POS payment-time capture of the aggregator order reference: when the cashier selects a payment method linked to an aggregator with "Require Order ID at Payment" enabled (e.g. Talabat), a popup asks for that aggregator's order number and blocks payment until it matches the configured digit length (default 10). Prompted again as a final check at payment validation in case the payment line was added another way (e.g. refunds).
- New Aggregator fields: `require_order_ref` (default on), `order_ref_digit_length` (default 10), editable on the Aggregator form.
- `online_aggregator_order_ref` now loads to the POS frontend (was backend-only) and is validated server-side (`_check_online_aggregator_order_ref`) as a safety net against malformed values saved outside the POS payment flow.

## 19.0.5.3.0
- Statement importer and order comparison export now require and check the statement's "Date / Time" column against the settlement's Date Start/End: rows outside that range are excluded from Actual totals and from the order comparison.
- Import Statement posts a chatter note when rows were excluded for being outside the settlement's date range.
- Statement template updated with the required Date / Time column.

## 19.0.5.2.0
- Added `online_aggregator_order_ref` on pos.order: the aggregator's own order number (Talabat "Order Id" etc.), entered manually in the back office, used as the join key for order-level reconciliation. Exposed on the POS order form and the Aggregator Sales Results report.
- Added "Export Order Comparison" button on Aggregator Settlement: exports a 3-sheet .xlsx (Matched / Talabat Not Matching POS / POS Not Matching Talabat), matching orders on that reference and comparing customer collections, contribution, and commission per order.
- Fixed variance_percent double-scaling (see 5.1.0 notes below) — now displays correctly with the percentage widget.
- Granted Finance Manager write access on pos.order (was read-only) so they can enter the aggregator order reference themselves.

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
