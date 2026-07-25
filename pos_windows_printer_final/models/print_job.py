# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class PrintJob(models.Model):
    _name = "print.job"
    _description = "Print Job Queue"
    _rec_name = "display_name"
    _inherit = ["mail.thread.main.attachment", "mail.activity.mixin"]

    name = fields.Char(string="Job Name", default="New Print Job")
    display_name = fields.Char(compute="_compute_display_name", store=True)

    printer_id = fields.Many2one("printer.printer", string="Printer")
    printer_name = fields.Char(string="Printer Name")
    print_engine_key = fields.Char(string="Print Engine Key")
    print_engine_client_id = fields.Many2one(
        "print.engine.client", string="Windows Host PC", ondelete="set null"
    )

    ip = fields.Char(string="Printer IP")
    port = fields.Integer(string="Printer Port", default=9100)
    printer_type = fields.Selection(
        [
            ("network", "IP/Network Printer"),
            ("usb", "USB Printer"),
            ("image", "Standard Image/PDF"),
            ("raw", "Zebra / Raw Text"),
        ],
        string="Printer Type",
        default="network"
    )
    is_open_cashbox = fields.Boolean(string="Open Cash Drawer?", default=False)

    image_data = fields.Binary(string="Print Data", attachment=True)
    print_type = fields.Selection(
        [("image", "Image / PDF"), ("raw", "Raw Text / ZPL")],
        string="Data Format",
        default="image",
        required=True
    )
    report_id = fields.Many2one("ir.actions.report", string="Report Source")

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("printing", "Printing"),
            ("done", "Completed"),
            ("error", "Failed"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True
    )

    error_message = fields.Text(string="Error Details")

    @api.depends("name", "printer_name", "create_date", "state")
    def _compute_display_name(self):
        for job in self:
            display = job.name or "Print Job"
            if job.printer_name:
                display = f"{display} → {job.printer_name}"
            if job.create_date:
                display = f"{display} ({job.create_date.strftime('%Y-%m-%d %H:%M')})"
            job.display_name = display

    def action_reprint(self):
        new_jobs = self.env["print.job"]
        for job in self:
            new_job = job.copy({
                "state": "draft",
                "error_message": False,
            })
            new_jobs += new_job

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Reprint Queued"),
                "message": _("%s print job(s) queued for reprinting.") % len(new_jobs),
                "type": "success",
            }
        }
