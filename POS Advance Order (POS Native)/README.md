# POS Advance Order (POS Native) - Odoo 19

## Goal
Create an **Advance Order** feature directly inside POS (no external HTML).

## Features
- Advance Order button in POS.
- Native Owl screen to capture:
  - Type: Pickup / Delivery
  - Requested date/time
  - Contact name, phone, address
  - Deposit, note
- Data stored on backend `pos.order` fields.
- Receipt shows Advance Order block when enabled.

## Install
1. Put folder `pos_advance_order_new` in your addons path.
2. Restart Odoo.
3. Apps -> Update Apps List
4. Install "POS Advance Order (POS Native)".

## Use
- In POS session: click **Advance Order** → fill fields → Save
- Finish sale normally (Payment → Validate)
- Backend: POS > Orders shows the fields (Advance Order page).
