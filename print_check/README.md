# Print Bank Cheque - Odoo 19 Module

## 🎯 Overview

A comprehensive cheque printing solution for Odoo 19 with full support for Jordanian and Arab country currencies. Features a modern, responsive UI with real-time cheque preview and Arabic Tafqeet (number-to-words conversion).

## ✨ Features

### Core Functionality
- **Real-time Cheque Preview** - See changes instantly as you type
- **Arabic Tafqeet** - Automatic conversion of amounts to Arabic words
- **21+ Currencies** - Support for all Arab and major international currencies
- **Customizable Positioning** - Adjust font size, weight, and position of all text fields
- **LocalStorage Persistence** - Your settings are saved between sessions

### RTL-Safe Design 🔒
This module is specifically designed to work correctly in both LTR and RTL (Arabic) Odoo interfaces. The layout **will not flip** when the database is switched to Arabic language.

**How it works:**
1. HTML `dir="ltr"` attributes on container elements
2. CSS isolation with scoped `.pc-ltr-isolated` class
3. JavaScript MutationObserver to enforce LTR on dynamic changes
4. Explicit `flex-direction: row !important` to prevent flex reversal

### UI Features
- **Tab-based Interface** - Organized controls for each cheque element
- **Arabic Honorific Shortcuts** - Quick insert buttons for السيد، السادة، etc.
- **Glassmorphism Design** - Modern, elegant appearance
- **Responsive Layout** - Works on tablets and smaller screens

## 📦 Installation

1. Copy the `print_check_final` folder to your Odoo addons directory
2. Update the apps list: `Settings > Apps > Update Apps List`
3. Install the module: Search for "Print Bank Cheque" and click Install

## 🚀 Usage

### From Payment Form
1. Go to `Accounting > Payments`
2. Open any outbound payment
3. Click the **🖨️ Print Check** button in the header

### Adjusting Settings
- **Payee Tab** - Name, font, alignment, position
- **Date Tab** - Date format and position
- **Amount Tab** - Number formatting, surrounds, numerals style
- **Words Tab** - Tafqeet settings, currency selection
- **Crossing Tab** - Crossing text and line style

### Printing
1. Adjust all settings as needed
2. Click the green **🖨️ طباعة الشيك / Print Cheque** button
3. A print dialog will open with the cheque positioned for printing

## 📁 Module Structure

```
print_check_final/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   └── print_check.py      # TransientModel & Payment extension
├── security/
│   └── ir.model.access.csv # Access rights
├── views/
│   ├── print_check_views.xml  # Main wizard form
│   └── payment_views.xml      # Payment form extension
└── static/
    └── src/
        ├── css/
        │   └── print_check.css  # Styles with RTL isolation
        ├── js/
        │   ├── print_check.js   # Main controller class
        │   └── tafqeet.js       # Arabic number-to-words
        └── cheque/
            └── jor-all.jpg      # Sample cheque background
```

## 🔧 Technical Details

### Supported Currencies

| Currency | Code | Fraction |
|----------|------|----------|
| Jordanian Dinar | JOD | فلس (1000) |
| Saudi Riyal | SAR | هللة (100) |
| UAE Dirham | AED | فلس (100) |
| Egyptian Pound | EGP | قرش (100) |
| Kuwaiti Dinar | KWD | فلس (1000) |
| Bahraini Dinar | BHD | فلس (1000) |
| Qatari Riyal | QAR | درهم (100) |
| Omani Riyal | OMR | بيسة (1000) |
| Iraqi Dinar | IQD | فلس (1000) |
| Syrian Pound | SYP | قرش (100) |
| Lebanese Pound | LBP | قرش (100) |
| Libyan Dinar | LYD | درهم (1000) |
| Sudanese Pound | SDG | قرش (100) |
| Yemeni Riyal | YER | فلس (100) |
| Moroccan Dirham | MAD | سنتيم (100) |
| Algerian Dinar | DZD | سنتيم (100) |
| Tunisian Dinar | TND | مليم (1000) |
| Israeli Shekel | ILS | أغورة (100) |
| US Dollar | USD | سنت (100) |
| Euro | EUR | سنت (100) |
| British Pound | GBP | بنس (100) |

### RTL Protection Layers

1. **HTML Attributes**: `dir="ltr"` on all critical containers
2. **Inline Styles**: `style="direction:ltr !important"` backup
3. **CSS Scoping**: All flex/grid rules scoped to `.pc-ltr-isolated`
4. **JavaScript Observer**: MutationObserver watches for RTL changes

## 🐛 Troubleshooting

### Layout Still Flipping in Arabic?
1. Clear browser cache (Ctrl+Shift+R)
2. Restart Odoo server to reload assets
3. Check browser console for errors

### Tafqeet Not Working?
1. Verify `tafqeet.js` is loaded (check console for "Tafqeet Library loaded")
2. Ensure amount is entered correctly (decimal with . not ,)

### Print Not Working?
1. Allow browser popups for your Odoo domain
2. Check that cheque image is loading

## 📄 License

OPL-1 (Odoo Proprietary License)

## 👨‍💻 Author

Agile Consulting - [agilemena.com](https://www.agilemena.com)

---

**Version:** 19.0.2.0.0  
**Odoo Compatibility:** 19.0  
**Last Updated:** 2024
