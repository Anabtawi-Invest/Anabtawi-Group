# -*- coding: utf-8 -*-
import secrets
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class PrintEngineClient(models.Model):
    _name = "print.engine.client"
    _description = "Print Engine Client (Windows Agent Host)"
    _rec_name = "name"
    _order = "name asc"
    _inherit = ["mail.thread.main.attachment", "mail.activity.mixin"]

    name = fields.Char(
        string="Host Computer Name",
        required=True,
        tracking=True,
        help="Name of the computer/system running the Windows Print Agent service."
    )
    active = fields.Boolean(
        string="Active",
        default=True,
        tracking=True
    )
    print_engine_key = fields.Char(
        string="Print Engine Key",
        readonly=True,
        copy=False,
        tracking=True,
        help="Unique authentication token for this Windows Print Agent host."
    )
    printer_ids = fields.One2many(
        "printer.printer",
        "print_engine_client_id",
        string="Installed Printers"
    )
    print_job_ids = fields.One2many(
        "print.job",
        "print_engine_client_id",
        string="Print Jobs"
    )

    @api.constrains("name")
    def _check_unique_name(self):
        for client in self:
            if self.search_count([("name", "=", client.name), ("id", "!=", client.id)]) > 0:
                raise ValidationError(_("A Windows Print Agent host with this name already exists. Please use a unique name."))

    @api.model_create_multi
    def create(self, vals_list):
        records = super(PrintEngineClient, self).create(vals_list)
        for record in records:
            record.generate_print_engine_key()
        return records

    def unlink(self):
        for client in self:
            if client.print_engine_key:
                client._remove_key_from_params()
        return super(PrintEngineClient, self).unlink()

    def generate_print_engine_key(self):
        self.ensure_one()
        if self.print_engine_key:
            self._remove_key_from_params()

        new_key = secrets.token_hex(16)
        self.print_engine_key = new_key

        param_obj = self.env["ir.config_parameter"].sudo()
        existing_keys = param_obj.get_param("cr_print_engine.key", "")
        keys_list = [k.strip() for k in existing_keys.split(",") if k.strip()]
        if new_key not in keys_list:
            keys_list.append(new_key)
        param_obj.set_param("cr_print_engine.key", ", ".join(keys_list))

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Key Generated"),
                "message": _("Print Engine Key generated successfully!"),
                "type": "success",
                "sticky": False,
            },
        }

    def _remove_key_from_params(self):
        self.ensure_one()
        if not self.print_engine_key:
            return
        param_obj = self.env["ir.config_parameter"].sudo()
        existing_keys = param_obj.get_param("cr_print_engine.key", "")
        if existing_keys:
            keys_list = [k.strip() for k in existing_keys.split(",") if k.strip() and k.strip() != self.print_engine_key]
            param_obj.set_param("cr_print_engine.key", ", ".join(keys_list))

    def sync_printers_from_engine(self, printers_data):
        self.ensure_one()
        if not printers_data:
            return {"status": "warning", "message": "No printers found", "created": 0, "updated": 0}

        created_count = 0
        updated_count = 0
        installed_names = set()

        for printer_data in printers_data:
            printer_name = (printer_data.get("name") or "").strip()
            if not printer_name:
                continue
            installed_names.add(printer_name)

            existing_printer = self.env["printer.printer"].with_context(active_test=False).search(
                [("name", "=", printer_name), ("print_engine_client_id", "=", self.id)],
                limit=1
            )
            if existing_printer:
                if not existing_printer.active:
                    existing_printer.active = True
                updated_count += 1
            else:
                self.env["printer.printer"].create({
                    "name": printer_name,
                    "print_engine_client_id": self.id,
                    "printer_type": "image",
                })
                created_count += 1

        stale_printers = self.env["printer.printer"].search([
            ("print_engine_client_id", "=", self.id),
            ("active", "=", True),
            ("name", "not in", list(installed_names)),
        ])
        stale_printers.active = False

        return {
            "status": "success",
            "message": f"Successfully synced {created_count + updated_count} printers",
            "created": created_count,
            "updated": updated_count,
            "archived": len(stale_printers),
        }

    @api.model
    def _load_pos_data_fields(self, config_id):
        return ['id', 'name', 'print_engine_key']

    @api.model
    def _load_pos_data_domain(self, data, config):
        return []

    @api.model
    def _load_pos_data_search_read(self, data, config):
        domain = self._load_pos_data_domain(data, config)
        fields = self._load_pos_data_fields(config)
        return self.search_read(domain, fields, load=False)
