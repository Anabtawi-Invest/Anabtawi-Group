# As-of Inventory Adjustment — Test Template

## CSV format (UTF-8, not Excel .xlsx)

### Minimal (recommended)
```csv
sku,quantity
810129329667,5
810129329674,0
```

- `sku` = barcode **or** Internal Reference (`default_code`)
- `quantity` = **true counted qty as of the As-of Date** (not today's target)

### Optional location column
```csv
sku,quantity,location
810129329667,5,NAKHL/Stock
```

If `location` is empty, the batch **Default Location** is used.

Accepted headers (any one):
- Product: `sku` | `barcode` | `default_code`
- Qty: `quantity` | `qty` | `counted`
- Location: `location` | `complete_name`

Sample files in this folder:
- `as_of_inventory_template.csv`
- `as_of_inventory_template_with_location.csv`

Replace SKUs with real products from your DB before upload.

---

## Quick test scenario (standard cost product)

Pick **1 product** with:
- type storable
- known Internal Reference / barcode
- stock in one location (e.g. NAKHL/Stock)
- preferably **standard cost**

### Setup numbers (example)
| Moment | Qty |
|--------|-----|
| System on hand **today** | note it (e.g. 10) |
| System on hand **as of 31/08 23:59:59** | Inventory → Reporting → Inventory at Date (e.g. 8) |
| Your sheet counted as of 31/08 | e.g. **5** |

Expected after Load:
- `qty_as_of` ≈ 8
- `qty_today` ≈ 10
- `correction` = 5 − 8 = **-3**
- `counted_to_apply` = 10 + (−3) = **7**
- state = **To Apply** (if correction ≠ 0)

### Steps in Odoo
1. Install/upgrade `pt_inventory_as_of_adjust`
2. Inventory → Operations → Adjustments → **As-of Inventory Adjustment**
3. New batch:
   - As-of Date: `2025-08-31 23:59:59` (use your real year)
   - Default Location: `NAKHL/Stock`
   - Accounting Date: same day `31/08` (optional but recommended)
   - Chunk size: `50` (or `1` for first test)
4. Upload CSV → **Load / Recompute Lines**
5. Review lines → **Confirm Apply**
6. Wait for cron (or run cron **As-of Inventory: Apply Chunks** manually)
7. Check:
   - line state = Applied
   - product on hand today ≈ `counted_to_apply`
   - Inventory → History / stock move: inventory move dated as-of date
   - Inventory at Date = as-of date → qty matches sheet

### Extra checks
| Case | Sheet qty vs qty_as_of | Expected line state |
|------|------------------------|---------------------|
| Same | equal | Skip |
| Different | ≠ | To Apply |
| Unknown SKU | — | Error |

### Do **not** use for first test
- Lot/serial tracked products (v1 has no lot column)
- `.xlsx` (save as CSV UTF-8)
