# POS Pledge Module - Installation Guide

## Files Created

### Backend (Python):
- `__init__.py` - Module initialization
- `__manifest__.py` - Module manifest
- `models/__init__.py` - Models initialization
- `models/product_template.py` - Product extensions (has_pledge, is_employee_service, is_delivery_service)
- `models/pos_pledge.py` - Main pledge model
- `models/pos_config.py` - POS config extensions (pledge/services accounts)
- `models/pos_order.py` - POS order filtering (excludes pledge items from invoices)

### Frontend (JavaScript):
- `static/src/js/models.js` - POS store extensions
- `static/src/js/pledge_popup.js` - Pledge configuration popup component
- `static/src/js/control_buttons_patch.js` - Control buttons patch (adds Pledge & Return buttons)
- `static/src/js/payment_screen.js` - Payment screen patch (creates pledge records)

### Frontend (XML Templates):
- `static/src/xml/pledge_popup.xml` - Pledge popup template
- `static/src/xml/control_buttons.xml` - Control buttons template (button UI)
- `static/src/xml/receipts.xml` - Receipt extensions (adds pledge marker)

### Data & Views:
- `data/sequence.xml` - Pledge reference sequence (PLEDGE/2026/00001)
- `data/product_data.xml` - Default pledge/employee/delivery products
- `views/product_template_views.xml` - Product form extensions
- `views/pos_pledge_views.xml` - Pledge list/form views
- `views/pos_config_views.xml` - POS config form extensions
- `security/ir.model.access.csv` - Access rights

## Installation Steps

### 1. Restart Odoo Server

```bash
# Stop Odoo if running
# Then restart with upgrade flag
cd /home/rana-faris/git/odoo19/odoo
./odoo-bin -u pos_pledge -d odoo19
```

### 2. Or Upgrade from UI

1. Go to Apps menu
2. Click "Update Apps List"
3. Search for "POS Pledge"
4. Click "Upgrade" if already installed, or "Install" if not

### 3. Configure POS Settings

1. Go to: **Point of Sale > Configuration > Point of Sale**
2. Select your POS
3. Scroll to bottom: "Pledge Management Configuration"
4. Set:
   - **Services Journal**: Sales Journal or Cash Journal
   - **Services Account**: Service Income account (e.g., 400000)
   - **Pledge Account**: Current Asset account (e.g., 101400)

### 4. Configure Products

The module creates 3 default products:
- **Pledge Item** (has_pledge = True)
- **Employee Service** (is_employee_service = True)
- **Delivery Service** (is_delivery_service = True)

You can modify these or create your own.

## Testing

### Test Case 1: Employee Service Only
1. Open POS session
2. Select customer
3. Add regular products
4. Add "Employee Service" product
5. Click "Pledge" button → Should show case 1 popup
6. Confirm and pay
7. Check that pledge record is created with employee journal entry

### Test Case 2: Pledge Only
1. Open POS session
2. Select customer
3. Add regular products
4. Add "Pledge Item" product
5. Click "Pledge" button → Should show case 2 popup
6. Confirm and pay
7. Check that pledge record is created with pledge journal entry

### Test Case 3: Pledge + Delivery
1. Open POS session
2. Select customer
3. Add regular products
4. Add "Pledge Item" product
5. Add "Delivery Service" product
6. Click "Pledge" button → Should show case 3 popup
7. Confirm and pay
8. Check that pledge record is created with both journal entries

### Test Pledge Return
1. Click "Return Pledge" button in POS
2. Select an active pledge
3. Confirm return
4. Check that reversal journal entry is created

## Troubleshooting

### Buttons don't appear
- Clear browser cache (Ctrl+Shift+R)
- Check browser console for errors
- Verify all assets loaded in manifest

### Accounting entries not created
- Check POS Configuration has all 3 accounts set
- Check Services Journal has default_account_id set
- Check journal is active

### Invoice includes pledge items
- Check `pos_order.py` is loaded
- Check product fields (has_pledge, etc.) are set correctly

## Next Steps

After successful installation:
1. Configure accounting accounts
2. Create/modify pledge products
3. Test all 3 business cases
4. Train users on pledge flow
5. Test pledge return process

## Module Structure

```
pos_pledge/
├── __init__.py
├── __manifest__.py
├── README.md
├── INSTALL.md
├── models/
│   ├── __init__.py
│   ├── product_template.py
│   ├── pos_pledge.py
│   ├── pos_config.py
│   └── pos_order.py
├── static/src/
│   ├── js/
│   │   ├── models.js
│   │   ├── pledge_popup.js
│   │   ├── control_buttons_patch.js
│   │   └── payment_screen.js
│   └── xml/
│       ├── pledge_popup.xml
│       ├── control_buttons.xml
│       └── receipts.xml
├── views/
│   ├── product_template_views.xml
│   ├── pos_pledge_views.xml
│   └── pos_config_views.xml
├── data/
│   ├── sequence.xml
│   └── product_data.xml
└── security/
    └── ir.model.access.csv
```

## Support

For issues or questions, refer to README.md for detailed documentation.
