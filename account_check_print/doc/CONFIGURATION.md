# Configuration Guide

## 1. Create a layout

As an Accounting Manager, open **Accounting → Configuration → Check Printing → Check Layouts**.
Create one layout per physical check design and company. Enter the exact paper
width and height in millimetres and the printer DPI. Upload a blank check image
for calibration. Logo and signature artwork are optional.

Click **Open Visual Designer**. Drag fields into place, resize them with the
lower-right handle, and click **Save**. Numeric coordinate inputs allow precise
calibration. Print a preview on plain paper and overlay it on the real stock
before issuing a live check.

## 2. Configure each bank journal

Open **Accounting → Configuration → Accounting → Journals**, select a bank
journal, and set the **Business Check Printing** section:

- Enable Check Printing
- Check Layout
- Next Check Number
- Print Language: English or Arabic
- Stock Type: Blank Stock prints the background; Pre-printed Stock prints data only

Each journal locks and advances its own number atomically. Never reuse a voided
number. To change stock ranges, set the next number before creating the first
check in the new range.

## 3. Issue checks

Create and confirm an outgoing vendor or miscellaneous payment from the enabled
bank journal. Accounting Users may preview. Accounting Managers may print the
first check. After printing, use **Reprint Check** or **Void Check**; both require
a reason and preserve the original number. The **Check History** smart button
shows the full audit trail.

## Printer calibration

Disable browser scaling and use actual size / 100%. Printer drivers can add
hardware margins even though the PDF is borderless. Correct any consistent
offset in the layout coordinates rather than in the report template.

