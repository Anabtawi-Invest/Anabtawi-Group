# POS Pledge (Rahn) Management Module

## Overview

This module enables managing pledge (Rahn) transactions in Odoo Point of Sale. It supports three business cases with automatic accounting entries, dual receipt generation, and pledge return functionality.

---

## Features

- ✅ **Product Configuration**: Mark products as pledge, employee service, or delivery service
- ✅ **Three Business Cases**: Employee, Pledge, and Pledge + Delivery scenarios
- ✅ **Dual Receipts**: Internal (full) and Customer (filtered) receipts
- ✅ **Accounting**: Automatic journal entries for pledges and services
- ✅ **Pledge Return**: Reversal entries when pledges are returned
- ✅ **Invoice Filtering**: Pledge/employee/delivery excluded from customer invoices

---

## Installation

1. Copy the `pos_pledge` folder to your Odoo addons directory
2. Update the apps list in Odoo
3. Install the "POS Pledge (Rahn) Management" module
4. Configure your POS settings (see Configuration section)

---

## Configuration

### 1. POS Configuration Settings

Go to: **Point of Sale > Configuration > Point of Sale**

Select your POS and configure the following fields:

#### Pledge Management Configuration (at the bottom of the form):

- **Pledge Product**: Product used to create the dedicated pledge collection POS order line

**Example Configuration:**
```
Pledge Product: Pledge Item
```

### 2. Product Configuration

Go to: **Products > Products**

#### For Pledge Products:
1. Create or edit a product
2. Set "Available in POS" = True
3. Check "Requires Pledge (Rahn)"
4. Set "Pledge Amount" (default pledge value)

#### For Employee Service:
1. Create a service product (e.g., "Employee Delivery Service")
2. Set "Available in POS" = True
3. Check "Is Employee Service"
4. Set the service price

#### For Delivery Service:
1. Create a service product (e.g., "Delivery Fee")
2. Set "Available in POS" = True
3. Check "Is Delivery Service"
4. Set the delivery fee

**Note**: Default products are created automatically during installation.

---

## Usage

### Case 1: Employee Service Only

**Scenario**: Employee handles everything (delivery + pledge collection)

**Steps**:
1. Open POS session
2. Select customer
3. Add regular products
4. Add the "Employee Service" product
5. Click the **"Pledge"** button (appears automatically)
6. Review pledge configuration popup
7. Confirm and proceed to payment
8. Two receipts will be printed:
   - **Internal Receipt**: Shows all items including employee service
   - **Customer Receipt**: Shows only products (no employee service)

**Accounting Entry**:
```
Debit: Cash/Bank            XXX
Credit: Services Income     XXX
```

---

### Case 2: Pledge Only

**Scenario**: Customer pledges an item (no delivery, no employee)

**Steps**:
1. Open POS session
2. Select customer
3. Add regular products
4. Add a **Pledge Product** (marked with "Requires Pledge")
5. Click the **"Pledge"** button
6. Review and confirm pledge amount
7. Proceed to payment
8. Two receipts will be printed:
   - **Internal Receipt**: Shows all items including pledge
   - **Customer Receipt**: Shows only regular products (no pledge)

**Accounting Entry**:
```
Debit: Cash/Bank            XXX
Credit: Pledge Liability    XXX
```

---

### Case 3: Pledge + Delivery

**Scenario**: Customer pledges an item AND requests delivery

**Steps**:
1. Open POS session
2. Select customer
3. Add regular products
4. Add a **Pledge Product**
5. Add a **Delivery Service** product
6. Click the **"Pledge"** button
7. Review pledge and delivery amounts
8. Proceed to payment
9. Two receipts will be printed

**Accounting Entries**:

For Pledge:
```
Debit: Cash/Bank            XXX
Credit: Pledge Liability    XXX
```

For Delivery:
```
Debit: Cash/Bank            XXX
Credit: Services Income     XXX
```

---

## Returning Pledges

When a customer returns a pledged item:

### Steps:
1. Open POS
2. Click the **"Return Pledge"** button
3. Select the pledge from the list
4. Confirm the return
5. A reversal journal entry is created automatically

### Reversal Entry:
```
Debit: Pledge Liability     XXX
Credit: Cash/Bank           XXX
```

---

## Receipt Behavior

### Internal Receipt (Full)
- Contains ALL items (products + pledge + employee + delivery)
- Marked with badges: **[PLEDGE]**, **[EMPLOYEE]**, **[DELIVERY]**
- Shows the business case type
- For internal records only

### Customer Receipt (Filtered)
- Contains ONLY regular products
- Does NOT show pledge/employee/delivery items
- Shows a note about pledge/services handled separately
- This is what the customer receives

---

## Invoice Behavior

When creating invoices from POS orders:

- ✅ **Regular products**: Included in customer invoice
- ❌ **Pledge products**: Excluded (handled via journal entries)
- ❌ **Employee service**: Excluded (handled via journal entries)
- ❌ **Delivery service**: Excluded (handled via journal entries)

**Customer invoice total = Regular products only**

---

## Technical Details

### Backend Models

#### `pos.pledge`
Tracks pledge transactions with:
- Partner, POS Order, Case Type
- Pledge/Employee/Delivery amounts
- Journal entry references
- State: Active, Returned, Cancelled

#### Extended `product.template`
New fields:
- `has_pledge`: Boolean
- `is_employee_service`: Boolean
- `is_delivery_service`: Boolean
- `pledge_amount`: Monetary

#### Extended `pos.config`
New fields:
- `pledge_product_id`: Product used to create dedicated pledge collection order lines

#### Extended `pos.order`
Overrides:
- `_get_order_lines_to_invoice()`: Filters out pledge/employee/delivery
- `_get_invoice_lines_values()`: Ensures exclusion from invoices

### Frontend Components

#### JavaScript Files:
- `models.js`: Order extensions with pledge detection methods
- `pledge_popup.js`: Popup for pledge configuration
- `pledge_button.js`: Button to initiate pledge flow
- `return_pledge_button.js`: Button to return pledges
- `payment_screen.js`: Payment screen override for pledge creation

#### Templates:
- `pledge_popup.xml`: Pledge configuration UI
- `pledge_button.xml`: Pledge button UI
- `return_pledge_button.xml`: Return pledge button UI
- `receipts.xml`: Dual receipt templates (internal + customer)

### Key Methods

#### Order Methods (Frontend):
- `detectPledgeCase()`: Returns 'case1', 'case2', 'case3', or null
- `getPledgeRelatedLines()`: Returns pledge/employee/delivery lines
- `getCustomerLines()`: Returns regular product lines only
- `getPledgeAmount()`: Total pledge amount
- `getEmployeeAmount()`: Total employee service amount
- `getDeliveryAmount()`: Total delivery service amount
- `hasPledgeItems()`: Boolean check

#### Backend Methods:
- `create_from_pos(vals)`: Creates pledge with accounting entries
- `_create_pledge_entry(amount, account, journal)`: Creates pledge journal entry
- `_create_service_entry(amount, account, journal, desc)`: Creates service journal entry
- `action_return_pledge()`: Handles pledge return with reversal

---

## Database Schema

### pos.pledge Table
```
- id: Integer (Primary Key)
- name: Char (Sequence: PLEDGE/YYYY/XXXXX)
- pos_order_id: Many2one(pos.order)
- pos_config_id: Many2one(pos.config)
- partner_id: Many2one(res.partner)
- case_type: Selection (case1, case2, case3)
- pledge_amount: Monetary
- employee_amount: Monetary
- delivery_amount: Monetary
- pledge_move_id: Many2one(account.move)
- employee_move_id: Many2one(account.move)
- delivery_move_id: Many2one(account.move)
- return_move_id: Many2one(account.move)
- state: Selection (active, returned, cancelled)
- pledge_products: Many2many(product.product)
- employee_product_id: Many2one(product.product)
- delivery_product_id: Many2one(product.product)
- return_date: Datetime
- company_id: Many2one(res.company)
- currency_id: Many2one(res.currency)
- create_date: Datetime
```

---

## Sequence

Pledge references follow this pattern:
```
PLEDGE/2026/00001
PLEDGE/2026/00002
...
```

---

## Security

Access rights are defined for:
- **POS User**: Read, Write, Create (no delete)
- **POS Manager**: Full access

---

## Menu Structure

```
Point of Sale
└── Pledges
    └── Pledge Records
```

---

## Troubleshooting

### Pledge button doesn't appear
- Ensure you have pledge, employee, or delivery products in the order
- Check that products are correctly configured with the pledge/employee/delivery flags

### Pledge order not created
- Verify POS Configuration has **Pledge Product** configured
- Verify order contains at least one pledge product with positive pledge amount

### Receipts showing all items
- The module generates TWO receipts: one internal (full) and one customer (filtered)
- Make sure you're giving the customer the "Customer Receipt"

### Invoice includes pledge items
- Verify the `pos_order.py` model extension is loaded
- Check that `has_pledge`, `is_employee_service`, and `is_delivery_service` fields are set on products

---

## Support & Customization

This module can be customized for:
- Custom accounting workflows
- Additional business cases
- Different receipt formats
- Integration with inventory/CRM

---

## Version

**Version**: 19.0.1.0.0  
**Odoo Version**: 19.0  
**License**: LGPL-3

---

## Author

Your Company

---

## Dependencies

- `point_of_sale`
- `account`

---

## Changelog

### Version 1.0.0
- Initial release
- Support for three business cases
- Dual receipt generation
- Automatic accounting entries
- Pledge return functionality
- Invoice filtering
