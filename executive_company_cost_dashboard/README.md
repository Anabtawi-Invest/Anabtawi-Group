# Executive Company Cost Dashboard (Odoo 19)

Chairman's cockpit for the Anabtawi Group: consolidated P&L, sister-company comparison,
branch leaderboard and cost intelligence on one screen. **Read-only** — it only runs `SELECT`
queries on posted journal items and never touches accounting records.

## Install / upgrade

1. Copy the folder to your addons path and restart Odoo.
2. Apps → update the app list → install **Executive Company Cost Dashboard**
   (or `-u executive_company_cost_dashboard` when upgrading from v1; the migration re-classifies accounts).
3. Give the Chairman user the group **Executive Cost Dashboard / Viewer** and enable **all companies**
   for that user (the dashboard only shows companies the user may access).
4. Open **Executive P&L → Dashboard**.

## How the numbers are built

| Dashboard | Source |
|---|---|
| Revenue / Cost of revenue / Operating expenses / Other income | Account **type** (Income, Cost of Revenue, Expenses + Depreciation, Other Income) — identical to Odoo's Profit & Loss report |
| Buckets (Rent, Payroll, Utilities, IT, Delivery…) | A second, functional split of the same accounts (Configuration → Account Classification) |
| Branches & departments | `analytic_distribution` of posted journal items, classified by Configuration → Branches & Departments |
| Branch sales fallback | POS net sales per POS (matched by the *POS Name Keywords* of the branch) — only when the ledger has no analytic revenue for that branch |

Only `posted` entries are counted. Previous-period comparison: month→previous month, quarter→previous
quarter, year/YTD/last 12 months→same span one year earlier, custom→equal span before.

## Smart Scanner

Configuration → Smart Scanner (also the **Smart Scan** button on the dashboard) classifies every P&L
account into a bucket (Arabic & English keywords + code prefixes, rules in `data/classification_rules.json`)
and every analytic account as branch / factory / department. Rows you edit by hand are flagged as manual
and never overwritten. Accounts created later are classified on the fly even before a re-scan.

## Tunable thresholds (Settings → Technical → System Parameters)

| Key | Default | Meaning |
|---|---|---|
| `ecd.branch_healthy_margin` | 10 | Net margin % at/above which a branch or company is *Healthy* |
| `ecd.rent_warn_pct` / `ecd.rent_danger_pct` | 15 / 20 | Rent as % of sales that raises a warning / alert |
| `ecd.delivery_warn_pct` | 8 | Delivery-platform commissions as % of revenue |
| `ecd.loss_warn_pct` | 1 | Waste & shrinkage as % of revenue |
| `ecd.cost_jump_pct` | 20 | Cost bucket growth vs previous period that raises an alert |

## Notes

* Amounts are summed as booked; no inter-company eliminations and no currency conversion.
* If **CEO Main Dashboard** (`ceo_main_dashboard`) is installed and the user has access, a
  *Purchasing Dashboard* button appears in the header (soft link, no dependency).
* Arabic (RTL) translation in `i18n/ar.po`.
