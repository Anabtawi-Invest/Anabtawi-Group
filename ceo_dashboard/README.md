# Executive CEO Dashboard (Odoo 19)

A single-screen executive dashboard covering Finance, Sales & CRM, Inventory,
HR, and Projects & Helpdesk, with global date filters (Today / Week / Month /
Year / Custom range) and year-over-year comparisons.

## Dependencies
`base`, `web`, `account`, `sale_management`, `crm`, `stock`, `purchase`,
`hr`, `hr_holidays`, `hr_attendance`, `hr_recruitment`, `project`, `helpdesk`

All of these must be installed — this build uses them as **hard
dependencies**, so installing this module will also install/activate all of
the above apps.

## Install
1. Copy the `ceo_dashboard` folder into your Odoo `addons` path.
2. Update Apps List, then install **Executive CEO Dashboard**.
3. Go to **Settings > Executive Dashboard** to set your Monthly Revenue
   Target, Monthly Billable Hours Target, and the "late check-in" cutoff time.
4. Open the **Executive Dashboard** app from the main menu.

## Notes / assumptions
- Figures use the `account_type` field on Chart of Accounts (income /
  income_other / expense / expense_direct_cost / expense_depreciation /
  asset_cash) to classify Revenue, COGS, Expenses and Cash — standard on any
  Odoo Chart of Accounts.
- Gross Profit = Revenue − COGS (accounts of type `expense_direct_cost`).
- DSO = (Accounts Receivable ÷ Period Revenue) × Days in the selected period.
- Stock Turnover = (COGS ÷ Current Inventory Value), annualized to the
  selected period length.
- "Late clock-in" and "Projects Over Budget" use simple, configurable
  heuristics (check-in time cutoff; planned vs. effective hours) since Odoo
  has no single canonical definition for either — adjust in
  `models/ceo_dashboard.py` if your business defines these differently.
- Every KPI section fails independently (try/except) so a missing field on
  one section never breaks the rest of the dashboard.

## License
LGPL-3
