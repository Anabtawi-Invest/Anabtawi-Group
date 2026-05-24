# pos_delivery_amount/README.md

# Delivery Amount – Odoo 19 Enterprise POS Module

## Overview

Enhances the Point of Sale session closing workflow to allow the cashier to record the cash amount that will be delivered (deposited) to the bank on the next business day.

A journal entry is automatically created and posted upon confirmation, ensuring full accounting integrity.

---

## Module Structure

```
pos_delivery_amount/
├── __init__.py
├── __manifest__.py
│
├── models/
│   ├── __init__.py
│   ├── pos_config.py          ← Adds delivery_intermediate_account_id, delivery_journal_id
│   └── pos_session.py         ← Adds delivery_amount, delivery_move_id + business logic
│
├── views/
│   ├── pos_config_views.xml   ← Inherits POS config form (Payment tab)
│   └── pos_session_views.xml  ← Inherits POS session form (Closing Control tab)
│
├── security/
│   └── ir.model.access.csv    ← Access rights
│
├── static/src/
│   ├── js/
│   │   ├── DeliveryAmountPopup.js         ← OWL popup component
│   │   └── ClosePosPopupExtension.js      ← Patches ClosePosPopup to inject flow
│   ├── xml/
│   │   └── DeliveryAmountPopup.xml        ← OWL template
│   └── css/
│       └── delivery_amount.css            ← Popup styling
│
├── i18n/
│   ├── pos_delivery_amount.pot            ← Translation template
│   └── ar.po                             ← Arabic translations
│
└── tests/
    ├── __init__.py
    └── test_delivery_amount.py            ← 11 mandatory test cases
```

---

## Installation

1. Copy the `pos_delivery_amount` folder into your Odoo `addons` directory.
2. Update the apps list: **Settings → Apps → Update Apps List**.
3. Search for **"Delivery Amount"** and click **Install**.

---

## Configuration (Required Before Use)

Navigate to **Point of Sale → Configuration → Settings → [Your POS] → Payment tab**:

| Field | Description |
|---|---|
| **Intermediate Account** | Temporary holding account for undeposited cash |
| **Delivery Journal** | Miscellaneous journal for the generated accounting entries |

Both fields are **mandatory** when the delivery amount is greater than zero.

---

## Workflow

```
Cashier clicks "Close Register"
        ↓
[ Delivery Amount Popup appears ]
        ↓
    Amount = 0 ?
    ├── YES → Zero Confirmation Popup
    │         ├── Yes → No journal entry, session closes
    │         └── No  → Return to Delivery Amount popup
    └── NO  → Validate amount ≤ cash balance
              ├── FAIL → Error shown, session blocked
              └── PASS → Create & post journal entry
                         → Chatter log added
                         → Session closes normally
```

---

## Accounting Entry (when amount > 0)

| Side | Account | Amount |
|---|---|---|
| **Debit** | Cash Account (POS Cash Journal) | delivery_amount |
| **Credit** | Intermediate Account (POS Config) | delivery_amount |

- **Journal**: Delivery Journal (Miscellaneous type)  
- **Date**: POS Session Closing Date  
- **Reference**: `Deliver Amount From {POS Name} - {Opening Date}`

---

## Validation Rules

| Rule | Behavior |
|---|---|
| Amount < 0 | Session blocked, error shown |
| Amount > counted cash balance | Session blocked, error shown |
| Amount = 0, confirmed | Session closes, no entry |
| Amount = 0, not confirmed | Returns to popup |
| Intermediate Account missing | Session blocked, error shown |
| Delivery Journal missing | Session blocked, error shown |
| Journal entry posting fails | Session blocked, full rollback |

---

## Translation Support

All UI strings support Arabic. The module ships with a complete `i18n/ar.po` file.

- **Frontend**: uses `_t()` from `@web/core/l10n/translation`
- **Backend**: uses `_()` from Odoo standard

---

## Running Tests

```bash
./odoo-bin -d your_database --test-tags=delivery_amount --stop-after-init
```

---

## Security Notes

- No `sudo()` used for accounting operations.
- No core Odoo files modified.
- No hardcoded IDs.
- Standard ORM used throughout.
- Standard Odoo access rights respected.

---

## Compatibility

| Item | Value |
|---|---|
| Odoo Version | 19.0 Enterprise |
| Edition | Enterprise |
| Currency | Single currency |
| License | LGPL-3 |
