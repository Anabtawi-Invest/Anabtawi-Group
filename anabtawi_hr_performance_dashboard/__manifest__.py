{
    "name": "Anabtawi HR Performance Dashboard",
    "summary": "ISO 30414 HR performance KPIs and dashboards for Anabtawi",
    "version": "19.0.1.0.0",
    "category": "Human Resources",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": ["hr", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "data/hr_kpi_data.xml",
        "views/hr_kpi_views.xml",
        "views/hr_kpi_menus.xml"
    ],
    "application": True,
    "installable": True
}
