# POS Multi-Branch IoT Printing

This Odoo 19 addon installs the official `pos_iot` integration. It does not
replace Odoo's printer service and does not use the browser print dialog.

## Required environment

- Odoo 19 Enterprise with an active IoT subscription.
- One Odoo IoT Box or Windows Virtual IoT installation in each branch.
- USB printers connected to the branch IoT system.
- LAN printers and the branch IoT system on the same local network.
- A static IP address for each LAN printer.

Bluetooth receipt printers are not supported by Odoo 19. Use the printer's USB
or LAN interface instead.

## Branch setup

1. Install or update this addon.
2. Install Windows Virtual IoT or an IoT Box in the branch.
3. Connect that IoT system to the Odoo database.
4. Associate it with the correct Point of Sale.
5. Confirm every printer appears under **IoT > Devices** and use its **Test**
   action before assigning it to a POS.
6. In the POS settings, enable **IoT Box** and select the receipt printer.
7. Enable **Automatic Receipt Printing** when receipts should print immediately
   after payment validation. Leave it disabled when the cashier should use
   **Print Receipt**.
8. In restaurant configurations, assign preparation printers and their product
   categories using Odoo's standard preparation-printer settings.
9. Connect a cash drawer to the receipt printer using the supported drawer
   port, then enable the cash drawer in the POS settings.

## Naming convention

Use a stable name such as:

`<BRANCH>-<POS>-<PURPOSE>`

Examples:

- `AMMAN-POS01-RECEIPT`
- `AMMAN-KITCHEN-HOT`
- `AMMAN-BAR`

## Important

Installing a printer in Windows is not by itself sufficient for silent browser
printing. The printer must also be detected and tested by Windows Virtual IoT.
Odoo then sends print jobs through the IoT service without opening a Windows or
browser print dialog.
