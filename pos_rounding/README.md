# POS Collect Later Module

## Overview

This module allows POS orders to be marked as "Collect Later" when customers pay in full but don't collect their orders immediately. The module maintains full accounting compliance (invoices remain paid) while providing operational tracking for uncollected orders.

## Features

1. **POS Option – "Collect Later"**
   - Add a checkbox in POS payment screen: "Collect Later"
   - When selected, a mandatory popup appears before payment completion:
     - Expected collection date (required)
     - Notes / remarks (optional)
   - Payment cannot be completed unless these details are provided

2. **Invoice Handling**
   - Invoice is created and fully paid as usual (no impact on accounting)
   - A new field "Collect Later" is added to the invoice for audit and reporting
   - Invoice remains in Paid state

3. **Operational Tracking Model**
   - Dedicated model `pos.collect.later.tracking` to track Paid but Uncollected POS Orders
   - Each record includes:
     - POS Order
     - Invoice
     - Customer
     - Paid amount
     - Expected collection date
     - Status flow: Pending Collection → Collected / Cancelled

4. **Employee View – Pending Collection Screen**
   - Dedicated menu item: "Pending Collection Orders"
   - View all paid but uncollected orders
   - Search by customer, order number, or date
   - Filter by status, date, overdue orders
   - Group by status, customer, or date

5. **Collection Process (When Customer Returns)**
   - Employee opens the original POS order
   - A button "Mark as Collected" is available
   - System automatically:
     - Removes/unchecks the "Collect Later" flag
     - Updates the tracking record status to Collected
   - No new invoices or payments are created

## Installation

1. Copy the module to `odoo/enbtawi/pos_collect_later`
2. Update the app list in Odoo
3. Install the module

## Usage

### In POS Frontend

1. Complete the order as usual
2. Click "Collect Later" checkbox in payment screen
3. A popup will appear asking for:
   - Expected collection date (required)
   - Collection notes (optional)
4. Complete payment - order will be marked as "Collect Later"

### In Backend

1. Go to Point of Sale → Pending Collection Orders
2. View all pending collection orders
3. Click on an order to view details
4. Click "Mark as Collected" when customer picks up the order

## Technical Details

### Models

- `pos.order`: Extended with fields:
  - `collect_later` (Boolean)
  - `expected_collection_date` (Date)
  - `collection_notes` (Text)
  - `is_collected` (Boolean)
  - `collect_later_tracking_id` (Many2one)

- `account.move`: Extended with field:
  - `collect_later` (Boolean, related from pos.order)

- `pos.collect.later.tracking`: New model with fields:
  - `pos_order_id` (Many2one)
  - `account_move_id` (Many2one)
  - `partner_id` (Many2one)
  - `amount_paid` (Monetary)
  - `expected_collection_date` (Date)
  - `collection_notes` (Text)
  - `state` (Selection: pending_collection, collected, cancelled)
  - `collected_date` (Datetime)
  - `collected_by` (Many2one)
  - `cancelled_date` (Datetime)
  - `cancelled_by` (Many2one)

### Frontend Components

- `CollectLaterPopup`: Popup component for entering collection details
- `PaymentScreenCollectLater`: Extended payment screen with collect later functionality
- `PosOrderCollectLater`: Extended POS order model with collect later fields

## Accounting Impact

- **No impact on accounting**: Invoices remain fully paid
- **No duplicate entries**: Payments are not duplicated
- **Full reconciliation**: All payments are properly reconciled
- **Audit trail**: Collect later flag is visible on invoices for reporting

## Security

- Access rights defined in `security/ir.model.access.csv`
- Users need appropriate permissions to view/manage tracking records

## Future Enhancements

- Email notifications for overdue collections
- SMS reminders for collection dates
- Reporting dashboard for collection statistics
- Integration with customer portal for self-service collection tracking
