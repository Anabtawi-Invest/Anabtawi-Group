# POS Advance Order (HTML Screen) - Odoo 19.0

## What it does
- Adds an **Advance Order** button in POS.
- Opens a custom POS screen to capture:
  - Requested Date/Time
  - Customer Note
- Saves values on the POS order and pushes them to backend `pos.order` fields:
  - `pos_adv_is_advance_order`
  - `pos_adv_requested_datetime`
  - `pos_adv_note`

## Install
1. Copy folder `pos_advance_order_html` into your Odoo addons path.
2. Restart Odoo.
3. Activate developer mode.
4. Apps -> Update Apps List.
5. Search: "POS Advance Order (HTML Screen)" -> Install.

## Where the data is stored
Backend model: `pos.order`

## Using your existing HTML file
- Your local file path (file:///C:/...) cannot be accessed by Odoo automatically.
- Copy only the BODY markup (no <script>) into:
  `static/src/xml/advance_order_templates.xml` inside the `pos-adv-custom-html` div.
- If you need JS behavior, implement it in:
  `static/src/js/advance_order_screen.js`
