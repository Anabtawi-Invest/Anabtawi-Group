{
  "name": "Branch Supply via Fleet (Manufacturing + Procurement)",
  "version": "19.0.2.0.0",
  "category": "Inventory",
  "summary": "Branch supply workflow with Fleet transit, MO auto-create on shortage, and procurement notification/PO draft.",
  "depends": ["stock", "mail", "account", "mrp", "purchase"],
  "data": [
    "security/ir.model.access.csv",
    "data/sequence.xml",
    "views/branch_supply_order_views.xml",
    "views/fleet_discrepancy_views.xml",
    "views/branch_supply_menus.xml"
  ],
  "installable": true,
  "application": false,
  "license": "LGPL-3"
}
