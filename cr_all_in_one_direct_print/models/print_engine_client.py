# -*- coding: utf-8 -*-
# Part of Creyox Technologies

import secrets
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import requests


class PrintEngineClient(models.Model):
    _name = "print.engine.client"
    _description = "Print Engine Client"
    _rec_name = "name"
    _order = "name asc"
    _inherit = ["mail.thread.main.attachment", "mail.activity.mixin"]

    name = fields.Char(
        string="Host System Name",
        required=True,
        tracking=True,
        help="Name of the computer/system where the print engine is installed",
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        tracking=True,
        help="Inactive print engine clients will not be available for printing",
    )

    print_engine_key = fields.Char(
        string="Print Engine Key",
        readonly=True,
        copy=False,
        tracking=True,
        help="Unique authentication key for this print engine client",
    )
    printer_ids = fields.One2many(
        "printer.printer",
        "print_engine_client_id",
        string="Printers",
        help="Printers connected to this print engine client",
    )

    print_job_ids = fields.One2many(
        "print.job",
        "print_engine_client_id",
        string="Print Jobs",
        help="Print jobs processed by this print engine client",
    )
    # # ========== PRINT PRIORITY ==========
    # default_priority = fields.Selection([
    #     ('0', 'Low'),
    #     ('1', 'Normal'),
    #     ('2', 'High'),
    #     ('3', 'Urgent')
    # ], string='Default Print Priority',
    #     default='1',
    #     help='Default priority level for print jobs from this report. '
    #          'Higher priority jobs print before lower priority jobs.')

    @api.constrains("name")
    def _check_unique_name(self):
        """Ensure print engine client name is unique."""
        for client in self:
            if (
                self.search_count([("name", "=", client.name), ("id", "!=", client.id)])
                > 0
            ):
                raise ValidationError(
                    _(
                        "A print engine client with this name already exists. Please use a unique name."
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        """Auto-generate print engine key at host system creation."""
        records = super(PrintEngineClient, self).create(vals_list)
        for record in records:
            record.generate_print_engine_key()
            record.message_post(
                body=_("Print Engine Client created with key: %s")
                % record.print_engine_key
            )
        return records

    def unlink(self):
        """Remove print engine key from system parameters before deletion."""
        for client in self:
            if client.print_engine_key:
                client._remove_key_from_params()

            client.message_post(body=_("Print Engine Client deleted"))

        return super(PrintEngineClient, self).unlink()

    def generate_print_engine_key(self):
        """Generate a new print engine key and update the configuration parameter."""
        self.ensure_one()

        if self.print_engine_key:
            raise ValidationError(
                _(
                    "Print Engine Key already exists. Use 'Regenerate Key' to create a new one."
                )
            )

        new_key = secrets.token_hex(16)
        self.print_engine_key = new_key

        print_engine_keys = (
            self.env["ir.config_parameter"].sudo().get_param("cr_print_engine.key", "")
        )
        if print_engine_keys:
            new_key = f"{new_key}, {print_engine_keys}"
        self.env["ir.config_parameter"].sudo().set_param("cr_print_engine.key", new_key)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Print Engine Key generated successfully!"),
                "type": "success",
                "sticky": False,
            },
        }

    def _remove_key_from_params(self):
        """Remove this client's key from system parameters."""
        self.ensure_one()

        if not self.print_engine_key:
            return

        print_engine_keys = (
            self.env["ir.config_parameter"].sudo().get_param("cr_print_engine.key", "")
        )
        if print_engine_keys:
            keys_list = [k.strip() for k in print_engine_keys.split(",")]
            if self.print_engine_key in keys_list:
                keys_list.remove(self.print_engine_key)
                new_keys = ", ".join(keys_list)
                self.env["ir.config_parameter"].sudo().set_param(
                    "cr_print_engine.key", new_keys
                )

    def sync_printers_from_engine(self, printers_data):
        """
        Sync printers discovered by print engine.
        Called from the print engine script via API.
        """
        self.ensure_one()

        if not printers_data:
            return {
                "status": "warning",
                "message": "No printers found on the system",
                "created": 0,
                "updated": 0,
                "skipped": 0,
            }

        created_count = 0
        updated_count = 0

        for idx, printer_data in enumerate(printers_data, start=1):
            printer_name = printer_data.get("name")

            if not printer_name:
                continue

            existing_printer = self.env["printer.printer"].search(
                [("name", "=", printer_name), ("print_engine_client_id", "=", self.id)],
                limit=1,
            )

            if existing_printer:

                updated_count += 1

            else:

                self.env["printer.printer"].create(
                    {
                        "name": printer_name,
                        "print_engine_client_id": self.id,
                    }
                )

                created_count += 1

        return {
            "status": "success",
            "message": f"Successfully synced {created_count + updated_count} printers",
            "created": created_count,
            "updated": updated_count,
            "skipped": 0,
        }
