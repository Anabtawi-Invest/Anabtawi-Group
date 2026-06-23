from odoo import fields, models


class DeliveryTransactionReportWizard(models.TransientModel):
    _name = "delivery.transaction.report.wizard"
    _description = "Delivery Transaction Report Wizard"

    report_date = fields.Date(
        string="Until Date",
        required=True,
        default=fields.Date.context_today,
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Location",
        domain="[('usage', '=', 'internal')]",
        help="Leave empty to include all locations.",
    )

    def action_print_report(self):
        self.ensure_one()
        report = self.env.ref(
            "internal_transfer_excel_report.action_report_delivery_transaction"
        )
        data = {
            "report_date": fields.Date.to_string(self.report_date),
            "location_id": self.location_id.id or False,
        }
        return report.report_action(self, data=data)
