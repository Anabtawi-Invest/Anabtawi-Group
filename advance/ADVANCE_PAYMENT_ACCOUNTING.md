# Advance Payment - Accounting Documentation

This document describes all financial movements (journal entries) that occur in the Advance Payment module and the accounts affected by each transaction.

---

## Overview

The Advance Payment module handles customer advance payments for POS orders. The accounting flow consists of two main phases:
1. **Initial Advance Payment**: Customer pays a partial amount (advance)
2. **Order Completion**: Invoice is created and remaining amount is paid

---

## Phase 1: Initial Advance Payment

When a customer makes an advance payment through the POS system.

### Transaction Flow

1. **Account Payment Created** (`account.payment`)
2. **POS Payment Created** (`pos.payment`)

### Journal Entry: Initial Advance Payment

When advance payment is created, an `account.payment` record is posted with the following entries:

#### For Cash Payment:
```
Account                          | Debit   | Credit
--------------------------------|---------|--------
Cash Journal (e.g., Cash Bakery)|  X.XX   |
Advance Account (Liability)     |         |  X.XX
```

#### For Card Payment:
```
Account                          | Debit   | Credit
--------------------------------|---------|--------
Card Journal (e.g., Bank)       |  X.XX   |
Advance Account (Liability)     |         |  X.XX
```

#### For Mixed Payment (Cash + Card):
Two separate `account.payment` records are created:

**Cash Component:**
```
Account                          | Debit   | Credit
--------------------------------|---------|--------
Cash Journal                     |  X.XX   |
Advance Account (Liability)     |         |  X.XX
```

**Card Component:**
```
Account                          | Debit   | Credit
--------------------------------|---------|--------
Card Journal                     |  Y.YY   |
Advance Account (Liability)     |         |  Y.YY
```

**Total:**
- Cash Amount + Card Amount = Total Advance Payment
- Advance Account (Liability) is credited with the total amount

### Code Reference
- **File**: `models/pos_advance_payment.py`
- **Method**: `create_from_pos()`
- **Lines**: 491-503 (Cash), 524-536 (Card), 563-575 (Single Payment)

### Accounts Used
- **Cash Journal**: `pos_config.pos_cash_journal_id` (e.g., "Cash Bakery")
- **Card Journal**: `pos_config.pos_card_journal_id` (e.g., "Bank")
- **Advance Account**: `pos_config.pos_advance_account_id` (e.g., "201000 Current Liabilities")

---

## Phase 2: Order Completion (Create Invoice)

When the customer completes the order and pays the remaining amount.

### Transaction Flow

1. **Invoice Created** (`account.move` - invoice)
2. **Second Payment Created** (`account.payment` - for remaining amount)
3. **Transfer Move Created** (`account.move` - to apply advance to invoice)
4. **Reconciliation** (automatically reconciles receivable lines)

---

### Step 2.1: Invoice Creation

When `action_create_invoice()` is called, a POS order is converted to an invoice.

#### Journal Entry: Invoice
```
Account                          | Debit   | Credit
--------------------------------|---------|--------
Account Receivable               |  X.XX   |
Product Sales                    |         |  Y.YY
Tax Account (e.g., Tax Received)|         |  Z.ZZ
```

**Example:**
- Total Invoice: $22.66
- Products: $19.70
- Tax (15%): $2.96

```
Account                          | Debit   | Credit
--------------------------------|---------|--------
Account Receivable               |  22.66  |
Product Sales                    |         |  19.70
Tax Received                     |         |   2.96
```

### Code Reference
- **File**: `models/pos_advance_payment.py`
- **Method**: `action_create_invoice()`
- **Line**: 888 - calls `pos_order._generate_pos_order_invoice()`

### Accounts Used
- **Account Receivable**: `partner.property_account_receivable_id`
- **Product Sales**: Product's `property_account_income_id`
- **Tax Account**: Tax's account (e.g., "251000 Tax Received")

---

### Step 2.2: Second Payment (Remaining Amount)

When the remaining amount is paid, an `account.payment` record is created.

#### Journal Entry: Second Payment
```
Account                          | Debit   | Credit
--------------------------------|---------|--------
Cash/Card Journal                |  X.XX   |
Account Receivable               |         |  X.XX
```

**Note**: The `destination_account_id` is explicitly set to `Account Receivable` (NOT Advance Account).

**Example:**
- Remaining Amount: $2.00

**For Cash:**
```
Account                          | Debit   | Credit
--------------------------------|---------|--------
Cash Journal                     |   2.00  |
Account Receivable               |         |   2.00
```

**For Card:**
```
Account                          | Debit   | Credit
--------------------------------|---------|--------
Card Journal                     |   2.00  |
Account Receivable               |         |   2.00
```

**For Mixed Payment:**
Two separate `account.payment` records are created (similar to advance payment).

### Code Reference
- **File**: `models/pos_advance_payment.py`
- **Method**: `action_create_invoice()`
- **Lines**: 
  - 803-816 (Cash - Mixed)
  - 831-844 (Card - Mixed)
  - 863-876 (Single Payment)

### Accounts Used
- **Cash Journal**: `pos_config.pos_cash_journal_id`
- **Card Journal**: `pos_config.pos_card_journal_id`
- **Account Receivable**: `partner.property_account_receivable_id` (explicitly set as `destination_account_id`)

---

### Step 2.3: Transfer Move (Apply Advance to Invoice)

To close the advance account and apply it to the invoice, a transfer journal entry is created.

#### Journal Entry: Transfer Move
```
Account                          | Debit   | Credit
--------------------------------|---------|--------
Advance Account (Liability)     |  X.XX   |
Account Receivable               |         |  X.XX
```

This entry:
- **Debits** the Advance Account to close/zero it out
- **Credits** the Account Receivable to reduce customer debt (apply advance to invoice)

**Example:**
- Advance Amount: $20.66

```
Account                          | Debit   | Credit
--------------------------------|---------|--------
Advance Account (201000)         |  20.66  |
Account Receivable               |         |  20.66
```

### Code Reference
- **File**: `models/pos_advance_payment.py`
- **Method**: `_create_advance_transfer_move()`
- **Lines**: 619-656

### Accounts Used
- **Advance Account**: `pos_config.pos_advance_account_id`
- **Account Receivable**: `partner.property_account_receivable_id`

---

### Step 2.4: Reconciliation

After all entries are created, the system automatically reconciles the Account Receivable lines from:
1. Invoice (Debit)
2. Second Payment (Credit)
3. Transfer Move (Credit)

#### Reconciliation Result:
```
Account Receivable Lines:
  + Invoice Debit:        $22.66
  - Second Payment Credit:  $2.00
  - Transfer Move Credit:  $20.66
  --------------------------------
  = Net Balance:          $0.00 ✓
```

All receivable lines are fully reconciled and balanced.

### Code Reference
- **File**: `models/pos_advance_payment.py`
- **Method**: `action_create_invoice()`
- **Lines**: 898-907

---

## Complete Example

Let's trace a complete example:
- **Total Order**: $22.66
- **Advance Paid**: $20.66 (Cash)
- **Remaining**: $2.00 (Cash)
- **Products**: $19.70
- **Tax**: $2.96

### Phase 1: Initial Advance Payment

**Entry 1: Advance Payment**
```
Account                          | Debit   | Credit
--------------------------------|---------|--------
Cash Journal                     |  20.66  |
Advance Account (201000)         |         |  20.66
```

**Balance Sheet Impact:**
- Cash/Bank: +$20.66
- Current Liabilities (Advance Account): +$20.66

---

### Phase 2: Order Completion

**Entry 2: Invoice**
```
Account                          | Debit   | Credit
--------------------------------|---------|--------
Account Receivable               |  22.66  |
Product Sales                    |         |  19.70
Tax Received                     |         |   2.96
```

**Entry 3: Second Payment**
```
Account                          | Debit   | Credit
--------------------------------|---------|--------
Cash Journal                     |   2.00  |
Account Receivable               |         |   2.00
```

**Entry 4: Transfer Move**
```
Account                          | Debit   | Credit
--------------------------------|---------|--------
Advance Account (201000)         |  20.66  |
Account Receivable               |         |  20.66
```

**Reconciliation:**
- Account Receivable: $22.66 - $2.00 - $20.66 = **$0.00** ✓
- Advance Account: $20.66 - $20.66 = **$0.00** ✓

---

## Final Account Balances

### After Complete Transaction:

| Account | Final Balance | Status |
|---------|---------------|--------|
| **Cash Journal** | +$22.66 | Increased (total payment received) |
| **Advance Account** | $0.00 | Balanced (closed/zeroed) |
| **Account Receivable** | $0.00 | Balanced (reconciled) |
| **Product Sales** | +$19.70 | Revenue recognized |
| **Tax Account** | +$2.96 | Tax collected |

---

## Important Notes

1. **Advance Account**: Must be a Liability account (e.g., "201000 Current Liabilities")
2. **Destination Account**: 
   - For advance payment: Always `Advance Account`
   - For second payment: Always `Account Receivable` (explicitly set)
3. **Session Closing**: Advance payments are **NOT** processed during POS session closing because they are already recorded via `account.payment`
4. **Reconciliation**: Happens automatically after all entries are created
5. **Mixed Payments**: Create separate `account.payment` records for cash and card components

---

## Configuration Requirements

To use this module, the following must be configured in POS Settings:

1. **POS Advance Account**: Liability account for advance payments
   - Field: `pos_config.pos_advance_account_id`
   - Example: "201000 Current Liabilities"

2. **POS Cash Journal**: Journal for cash payments
   - Field: `pos_config.pos_cash_journal_id`
   - Example: "Cash Bakery"

3. **POS Card Journal**: Journal for card payments
   - Field: `pos_config.pos_card_journal_id`
   - Example: "Bank"

---

## Related Files

- `models/pos_advance_payment.py`: Main model handling advance payments
- `models/pos_session.py`: Session closing logic (advance payments skipped)
- `models/pos_config.py`: POS configuration with advance account fields

---

---

## Odoo Standard Behavior vs Advance Payment Module

### Standard Odoo POS Payment Flow

In **standard Odoo POS**, when a payment is made:

1. **Only `pos.payment` is created** - This records the payment in the POS system
2. **No `account.payment` is created automatically** - Payment accounting entries are handled differently
3. **`account.move` is created later** when:
   - An invoice is generated (via `pos.payment._create_payment_moves()`)
   - Or during session closing (aggregated/combined payments)

**Important Points:**
- `pos.payment` is created immediately when payment is made in POS
- `account.payment` is **only** created in specific cases:
  - During session closing for **combined payments** (aggregated by payment method)
  - For **split transactions** (when `split_transactions = True` on payment method)
- When invoice is created, `pos.payment._create_payment_moves()` creates `account.move` directly (not `account.payment`)

### Advance Payment Module Behavior

In the **Advance Payment module**, the behavior is **different**:

1. **Both `pos.payment` AND `account.payment` are created immediately** when advance payment is made
2. **`account.payment` is created explicitly** to:
   - Record the advance payment immediately in accounting
   - Use `destination_account_id = Advance Account` (not Receivable Account)
   - Allow proper tracking of advance payments as liabilities

**Why This Difference?**

The Advance Payment module needs to:
- Record advance payments as **liabilities** (Advance Account) immediately
- Track advance payments separately from normal POS payments
- Apply advance payments to invoices later (via Transfer Move)
- Ensure proper accounting without waiting for invoice or session closing

### Comparison Table

| Aspect | Standard Odoo POS | Advance Payment Module |
|--------|-------------------|------------------------|
| **`pos.payment`** | ✅ Created immediately | ✅ Created immediately |
| **`account.payment`** | ❌ Not created (only in session closing for combined/split payments) | ✅ Created immediately |
| **`account.move`** | Created when invoice is generated | Created via `account.payment` immediately |
| **Destination Account** | Receivable Account (when invoice created) | Advance Account (Liability) |
| **Accounting Timing** | When invoice created or session closed | Immediately when advance paid |
| **Purpose** | Standard POS payment flow | Track advance payments as liabilities |

### Code Reference

**Standard Odoo:**
- File: `addons/point_of_sale/models/pos_payment.py`
- Method: `_create_payment_moves()` (creates `account.move` directly)
- Lines: 72-120

**Advance Payment Module:**
- File: `enbtawi/advance/models/pos_advance_payment.py`
- Method: `create_from_pos()` (creates both `pos.payment` and `account.payment`)
- Lines: 491-575

---

## Reports and Accounting Visibility

### Does `pos.payment` Appear in Accounting Reports?

**No**, `pos.payment` does **NOT** appear in accounting reports. It is a POS-only record used for:
- Tracking payments in POS system
- POS reports (e.g., POS Orders Report, Sales Details)
- Display in POS session closing
- **NOT** in accounting reports (Balance Sheet, Profit & Loss, etc.)

### Does `account.payment` Appear in Accounting Reports?

**Yes**, `account.payment` appears in accounting reports **through its `account.move`** (journal entry). When `account.payment.action_post()` is called, it creates an `account.move` which:
- Appears in all accounting reports
- Shows in Balance Sheet, Profit & Loss, etc.
- Is the **only** accounting entry visible in reports

### Will It Appear as Two Payments?

**No, it will NOT appear as two payments** in accounting reports because:

1. **`pos.payment` is NOT included in accounting reports**
   - It's a POS-only record
   - Does not create `account.move` directly
   - Not visible in accounting reports

2. **Only `account.payment` creates accounting entries**
   - Creates one `account.move` when posted
   - This `account.move` is the only entry visible in accounting reports

3. **Advance payments are skipped in session closing**
   - In `pos_session._accumulate_amounts()`, advance payments are skipped (line 153)
   - This prevents double counting
   - Only the `account.payment` entry is used for accounting

### Example: What Appears in Reports

**For a $20.66 advance payment:**

#### In POS Reports:
- ✅ `pos.payment` appears (POS Orders, Sales Details)
- ✅ Shows payment method, amount, date

#### In Accounting Reports:
- ✅ Only `account.move` from `account.payment` appears
- ✅ Shows: Debit Cash/Bank, Credit Advance Account
- ❌ `pos.payment` does NOT appear

#### Result:
- **One accounting entry** appears in reports (not two)
- The entry shows the advance payment correctly
- No double counting occurs

### Important Notes

1. **`pos.payment` is for POS tracking only**
   - Helps track payments in POS system
   - Not part of accounting entries
   - Skipped in session closing for advance orders

2. **`account.payment` is for accounting**
   - Creates the actual accounting entry
   - Visible in all accounting reports
   - This is the "real" payment from accounting perspective

3. **Session Closing Behavior**
   - Advance payments are skipped in `_accumulate_amounts()` (line 153)
   - This ensures `account.payment` entry is not duplicated
   - Only one accounting entry exists per advance payment

### Code Reference

**Skipping Advance Payments in Session Closing:**
- File: `enbtawi/advance/models/pos_session.py`
- Method: `_accumulate_amounts()`
- Lines: 153-160

```python
if is_advance_order and payment_type != 'pay_later':
    # Skip - payment already has journal entry from account.payment
    continue
```

This ensures that `pos.payment` is NOT processed again in session closing because `account.payment` already created the accounting entry.

---

## Version

- **Module**: `enbtawi/advance`
- **Odoo Version**: 19.0
- **Documentation Date**: 2026-01-19
