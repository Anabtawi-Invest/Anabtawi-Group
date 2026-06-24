
{
    "name": "Soft HR KPI Dashboard",
    "version": "19.0.1.1.0",
    "depends": ["hr","account","web"],
    "data": [
        "security/ir.model.access.csv",
        "security/record_rules.xml",
        "views/dashboard_action.xml",
        "views/menus.xml",
        "data/cron_jobs.xml"
    ],
    "assets": {
        "web.assets_backend": []
    },
    "installable": True
}
