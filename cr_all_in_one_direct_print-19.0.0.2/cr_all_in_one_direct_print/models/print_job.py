# -*- coding: utf-8 -*-
# Part of Creyox Technologies

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import requests
import base64
import logging

class PrintJob(models.Model):
    _name = "print.job"
    _description = "Print Job"
    _rec_name = "display_name"
    _inherit = [
        "mail.thread.main.attachment",
        "mail.activity.mixin",
    ]

    name = fields.Char(
        string="Job Name",
        default="New Print Job",
    )
    display_name = fields.Char(
        string="Display Name",
        compute="_compute_display_name",
        store=True,
    )

    printer_id = fields.Many2one(
        "printer.printer",
        string="Printer",
    )
    printer_name = fields.Char(
        string="Printer Name",
    )

    print_engine_key = fields.Char(
        string="Print Engine Key",
    )
    print_engine_client_id = fields.Many2one(
        "print.engine.client", string="Print Engine Client", ondelete="set null"
    )

    image_data = fields.Binary(string="Print Data", attachment=True) 
    print_type = fields.Selection(
        [
            ("image", "Image / PDF"),
            ("raw", "Raw Text / ZPL"),
        ],
        string="Data Type",
        default="image",
        required=True,
    )
    report_id = fields.Many2one(
        "ir.actions.report",
        string="Report",
        help="Report that generated this print job",
    )

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
        tracking=True,
    )

    # priority = fields.Selection([
    #     ('0', 'Low'),
    #     ('1', 'Normal'),
    #     ('2', 'High'),
    #     ('3', 'Urgent')
    # ], string='Priority', default='1', required=True,  )
    #

    # ========== ERROR HANDLING ==========
    error_message = fields.Text(string="Error Message")
    error_code = fields.Char(string="Error Code")
    @api.depends("name", "printer_name", "create_date", "state")
    def _compute_display_name(self):
        """Generate user-friendly display name for print job."""
        for job in self:
            display = "Print Job"
            if job.name and job.name != "New Print Job":
                display = job.name 

            if job.printer_name:
                display = f"{display} → {job.printer_name}"

            if job.create_date:
                display = f"{display} ({job.create_date.strftime('%Y-%m-%d %H:%M')})"

            job.display_name = display

    def action_reprint(self):
        """Create new print jobs with same data (reprint)."""
        new_jobs = self.env["print.job"]
        for job in self:
            new_job = job.copy(
                {
                    "state": "draft",
                    "error_message": False,
                    "error_code": False,
                }
            )
            new_jobs += new_job

        if len(self) == 1:
            return {
                "type": "ir.actions.act_window",
                "name": _("Reprint Job"),
                "res_model": "print.job",
                "res_id": new_jobs.id,
                "view_mode": "form",
                "target": "current",
            }
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reprint'),
                'message': _('%s jobs queued for reprinting.') % len(new_jobs),
                'type': 'success',
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }
