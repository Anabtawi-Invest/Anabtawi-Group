# Historical Data Import Templates

Ready-to-fill CSV templates for loading pre-launch data. These files are **not**
installed with the module — they are helpers you open in Excel/LibreOffice,
complete, and import through Odoo's standard **Import records** feature.

All files are UTF-8 so Arabic branch/factor names import correctly.

## How to import

1. Open the target list in Odoo:
   - *Quality → Branch Quality Control → Configuration → Historical Data → Historical Scores*
   - *… → Historical Data → Factor Averages*
   - *… → Configuration → Branches* (for adding branches)
2. Click the gear / **Favorites → Import records**.
3. Upload the matching CSV, map the columns (Odoo auto-matches the headers),
   and import.

## Files

### `branch_historical_scores_template.csv`
Overall branch results before the module went live. One row per branch per period.

| Column | Meaning |
|---|---|
| `branch_id` | Branch **name** (matched to an existing `qc.branch`). |
| `name` | Period label, e.g. `2025 Baseline`, `Q4 2024`. |
| `period_date` | Date used on trend charts (`YYYY-MM-DD`). |
| `total_score` | Overall score out of 100. Grade is derived automatically. |
| `source` | Free-text origin note. |

The 21 branch rows are pre-filled; the four scores known from the summary
(شفا بدران 86, العقبة أيلا 83, مرج الحمام 80, القويسمة 54) are filled in — add
the remaining scores before importing.

### `factor_averages_template.csv`
The ten overall factor averages (out of 10) from the historical summary. Per
branch-by-factor detail is **not** available in the source data, so this holds
one average per factor per period.

### `branches_template.csv`
For creating additional branches. `inspection_frequency` accepts
`weekly|monthly|quarterly|semiannual|annual`. `manager_id`/`inspector_id` are
user names (leave blank if unknown).

## Note
Detailed per-branch, per-factor history requires the original Excel/source data
and is out of scope of these overall-summary templates.
