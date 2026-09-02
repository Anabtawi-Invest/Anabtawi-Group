# -*- coding: utf-8 -*-
from datetime import datetime, time

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class BranchSupplyFlowSnapshotWizard(models.TransientModel):
    _name = "branch.supply.flow.snapshot.wizard"
    _description = "Branch Supply Flow Snapshot Wizard"

    date_from = fields.Datetime(
        string="From (Effective Date)",
        required=True,
        default=lambda self: datetime.combine(
            fields.Date.context_today(self).replace(day=1), time.min
        ),
    )
    date_to = fields.Datetime(
        string="To (Effective Date)",
        required=True,
        default=lambda self: datetime.combine(fields.Date.context_today(self), time.max),
    )
    all_branch_locations = fields.Boolean(string="All Branch Locations", default=True)
    location_id = fields.Many2one(
        "stock.location",
        string="Branch Location",
        domain="[('usage', '=', 'internal')]",
    )
    all_dispatch_operation_types = fields.Boolean(string="All Dispatch Operation Types", default=True)
    dispatch_picking_type_ids = fields.Many2many(
        "stock.picking.type",
        "branch_supply_flow_snap_wiz_dispatch_pt_rel",
        "wizard_id",
        "picking_type_id",
        string="Dispatch Operation Types",
        domain="[('code', '=', 'internal')]",
    )
    all_receipt_operation_types = fields.Boolean(string="All Receipt Operation Types", default=True)
    receipt_picking_type_ids = fields.Many2many(
        "stock.picking.type",
        "branch_supply_flow_snap_wiz_receipt_pt_rel",
        "wizard_id",
        "picking_type_id",
        string="Receipt Operation Types",
        domain="[('code', '=', 'internal')]",
    )
    all_pos_configs = fields.Boolean(string="All POS Branches", default=True)
    pos_config_ids = fields.Many2many("pos.config", string="POS Branches")
    replace_auto_snapshot = fields.Boolean(
        string="Replace Auto Snapshot for Period",
        default=False,
        help="If enabled, replaces the existing auto snapshot for the same calendar month.",
    )

    @api.onchange("all_branch_locations")
    def _onchange_all_branch_locations(self):
        if self.all_branch_locations:
            self.location_id = False

    @api.onchange("all_dispatch_operation_types")
    def _onchange_all_dispatch_operation_types(self):
        if self.all_dispatch_operation_types:
            self.dispatch_picking_type_ids = [(5, 0, 0)]

    @api.onchange("all_receipt_operation_types")
    def _onchange_all_receipt_operation_types(self):
        if self.all_receipt_operation_types:
            self.receipt_picking_type_ids = [(5, 0, 0)]

    @api.onchange("all_pos_configs")
    def _onchange_all_pos_configs(self):
        if self.all_pos_configs:
            self.pos_config_ids = [(5, 0, 0)]

    def _get_report_wizard_vals(self):
        self.ensure_one()
        return {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "all_branch_locations": self.all_branch_locations,
            "location_id": self.location_id.id if self.location_id else False,
            "all_dispatch_operation_types": self.all_dispatch_operation_types,
            "dispatch_picking_type_ids": [(6, 0, self.dispatch_picking_type_ids.ids)],
            "all_receipt_operation_types": self.all_receipt_operation_types,
            "receipt_picking_type_ids": [(6, 0, self.receipt_picking_type_ids.ids)],
            "all_pos_configs": self.all_pos_configs,
            "pos_config_ids": [(6, 0, self.pos_config_ids.ids)],
        }

    def _build_line_vals_list(self):
        self.ensure_one()
        report_wizard = self.env["branch.supply.flow.wizard"].create(self._get_report_wizard_vals())
        return report_wizard._build_report_values()

    def action_create_snapshot(self):
        self.ensure_one()
        line_vals_list = self._build_line_vals_list()
        if not line_vals_list:
            raise UserError(_("No data found for the selected filters."))

        Snapshot = self.env["branch.supply.flow.snapshot"]
        snapshot_vals = {
            "name": Snapshot._format_snapshot_name(self.date_from, self.date_to),
            "date_from": self.date_from,
            "date_to": self.date_to,
            "company_id": self.env.company.id,
            "all_branch_locations": self.all_branch_locations,
            "location_id": self.location_id.id if self.location_id else False,
        }

        if self.replace_auto_snapshot:
            period_key = fields.Date.to_date(self.date_to).strftime("%Y-%m")
            snapshot_vals.update({
                "is_auto": True,
                "period_key": period_key,
                "name": Snapshot._format_snapshot_name(self.date_from, self.date_to, is_auto=True),
            })
            snapshot = Snapshot._replace_auto_snapshot(period_key, snapshot_vals, line_vals_list)
        else:
            snapshot = Snapshot.create_from_report_values(snapshot_vals, line_vals_list)

        return {
            "name": _("Branch Supply Flow Snapshot"),
            "type": "ir.actions.act_window",
            "res_model": "branch.supply.flow.snapshot",
            "res_id": snapshot.id,
            "view_mode": "form",
            "target": "current",
        }
