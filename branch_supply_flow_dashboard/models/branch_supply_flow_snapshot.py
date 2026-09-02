# -*- coding: utf-8 -*-
from datetime import datetime, time

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class BranchSupplyFlowSnapshot(models.Model):
    _name = "branch.supply.flow.snapshot"
    _description = "Branch Supply Flow Snapshot"
    _order = "snapshot_date desc, id desc"

    name = fields.Char(string="Snapshot", required=True, readonly=True)
    snapshot_date = fields.Datetime(
        string="Generated On",
        default=fields.Datetime.now,
        required=True,
        readonly=True,
    )
    date_from = fields.Datetime(string="Period From", required=True, readonly=True)
    date_to = fields.Datetime(string="Period To", required=True, readonly=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        readonly=True,
        default=lambda self: self.env.company,
    )
    is_auto = fields.Boolean(string="Auto Generated", default=False, readonly=True)
    period_key = fields.Char(
        string="Period Key",
        readonly=True,
        help="Used to update recurring auto snapshots for the same period.",
    )
    all_branch_locations = fields.Boolean(string="All Branch Locations", readonly=True)
    location_id = fields.Many2one("stock.location", string="Branch Location", readonly=True)
    line_ids = fields.One2many(
        "branch.supply.flow.snapshot.line",
        "snapshot_id",
        string="Lines",
        readonly=True,
    )
    line_count = fields.Integer(compute="_compute_totals", store=True)
    total_requested_qty = fields.Float(
        string="Total Requested",
        digits="Product Unit",
        compute="_compute_totals",
        store=True,
    )
    total_sent_qty = fields.Float(
        string="Total Sent",
        digits="Product Unit",
        compute="_compute_totals",
        store=True,
    )
    total_received_qty = fields.Float(
        string="Total Received",
        digits="Product Unit",
        compute="_compute_totals",
        store=True,
    )
    total_sold_qty = fields.Float(
        string="Total Sold",
        digits="Product Unit",
        compute="_compute_totals",
        store=True,
    )
    total_unsold_qty = fields.Float(
        string="Unsold Stock",
        digits="Product Unit",
        compute="_compute_totals",
        store=True,
    )
    fill_rate = fields.Float(
        string="Fill Rate %",
        digits=(16, 2),
        compute="_compute_totals",
        store=True,
    )
    transit_loss_rate = fields.Float(
        string="Transit Loss %",
        digits=(16, 2),
        compute="_compute_totals",
        store=True,
    )
    sell_through_rate = fields.Float(
        string="Sell-through %",
        digits=(16, 2),
        compute="_compute_totals",
        store=True,
    )
    issue_line_count = fields.Integer(
        string="Issue Lines",
        compute="_compute_totals",
        store=True,
        help="Lines with transit loss, low sell-through, or unsold stock.",
    )

    @api.depends(
        "line_ids.requested_qty",
        "line_ids.sent_qty",
        "line_ids.received_qty",
        "line_ids.sold_qty",
        "line_ids.variance_received_sold",
        "line_ids.has_issue",
    )
    def _compute_totals(self):
        for snapshot in self:
            lines = snapshot.line_ids
            requested = sum(lines.mapped("requested_qty"))
            sent = sum(lines.mapped("sent_qty"))
            received = sum(lines.mapped("received_qty"))
            sold = sum(lines.mapped("sold_qty"))
            unsold = sum(lines.mapped("variance_received_sold"))

            snapshot.line_count = len(lines)
            snapshot.total_requested_qty = requested
            snapshot.total_sent_qty = sent
            snapshot.total_received_qty = received
            snapshot.total_sold_qty = sold
            snapshot.total_unsold_qty = unsold
            snapshot.fill_rate = (received / requested * 100.0) if requested else 0.0
            snapshot.transit_loss_rate = ((sent - received) / sent * 100.0) if sent else 0.0
            snapshot.sell_through_rate = (sold / received * 100.0) if received else 0.0
            snapshot.issue_line_count = len(lines.filtered("has_issue"))

    @api.model
    def _format_snapshot_name(self, date_from, date_to, is_auto=False):
        date_from_display = fields.Datetime.to_string(date_from)[:10]
        date_to_display = fields.Datetime.to_string(date_to)[:10]
        prefix = _("Auto") if is_auto else _("Snapshot")
        return f"{prefix}: {date_from_display} → {date_to_display}"

    @api.model
    def create_from_report_values(self, vals, line_vals_list):
        if not line_vals_list:
            raise UserError(_("No data found for the selected filters."))

        snapshot = self.create(vals)
        self.env["branch.supply.flow.snapshot.line"].create([
            dict(line_vals, snapshot_id=snapshot.id) for line_vals in line_vals_list
        ])
        return snapshot

    @api.model
    def _replace_auto_snapshot(self, period_key, snapshot_vals, line_vals_list):
        existing = self.search([
            ("is_auto", "=", True),
            ("period_key", "=", period_key),
            ("company_id", "=", snapshot_vals.get("company_id", self.env.company.id)),
        ], limit=1)
        if existing:
            existing.line_ids.unlink()
            existing.unlink()
        return self.create_from_report_values(snapshot_vals, line_vals_list)

    @api.model
    def _cron_refresh_current_month_snapshot(self):
        today = fields.Date.context_today(self)
        date_from = datetime.combine(today.replace(day=1), time.min)
        date_to = datetime.combine(today, time.max)
        period_key = today.strftime("%Y-%m")

        for company in self.env["res.company"].search([]):
            wizard = self.env["branch.supply.flow.wizard"].with_company(company).create({
                "date_from": date_from,
                "date_to": date_to,
                "all_branch_locations": True,
                "all_dispatch_operation_types": True,
                "all_receipt_operation_types": True,
                "all_pos_configs": True,
            })
            line_vals_list = wizard._build_report_values()
            if not line_vals_list:
                continue

            snapshot_vals = {
                "name": self._format_snapshot_name(date_from, date_to, is_auto=True),
                "date_from": date_from,
                "date_to": date_to,
                "company_id": company.id,
                "is_auto": True,
                "period_key": period_key,
                "all_branch_locations": True,
            }
            self.with_company(company)._replace_auto_snapshot(
                period_key, snapshot_vals, line_vals_list
            )

    def action_open_lines(self):
        self.ensure_one()
        return {
            "name": _("Supply Flow Lines"),
            "type": "ir.actions.act_window",
            "res_model": "branch.supply.flow.snapshot.line",
            "view_mode": "list,graph,pivot",
            "domain": [("snapshot_id", "=", self.id)],
            "context": {
                "search_default_group_by_location": 1,
            },
        }

    def action_open_issues(self):
        self.ensure_one()
        return {
            "name": _("Supply Flow Issues"),
            "type": "ir.actions.act_window",
            "res_model": "branch.supply.flow.snapshot.line",
            "view_mode": "list,graph,pivot",
            "domain": [
                ("snapshot_id", "=", self.id),
                ("has_issue", "=", True),
            ],
            "context": {
                "search_default_group_by_location": 1,
            },
        }

    def action_open_branch_comparison(self):
        self.ensure_one()
        return {
            "name": _("Branch Comparison"),
            "type": "ir.actions.act_window",
            "res_model": "branch.supply.flow.snapshot.line",
            "view_mode": "graph,pivot,list",
            "domain": [("snapshot_id", "=", self.id)],
            "context": {
                "graph_measure": "received_qty",
                "graph_groupbys": ["location_id"],
            },
        }

    def action_open_funnel(self):
        self.ensure_one()
        return {
            "name": _("Supply Funnel"),
            "type": "ir.actions.act_window",
            "res_model": "branch.supply.flow.snapshot.line",
            "view_mode": "graph,pivot,list",
            "domain": [("snapshot_id", "=", self.id)],
            "context": {
                "graph_measure": "requested_qty",
            },
        }

    @api.model
    def action_open_main_dashboard(self):
        latest = self.search([], order="snapshot_date desc, id desc", limit=1)
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "branch_supply_flow_dashboard.action_branch_supply_flow_dashboard"
        )
        if latest:
            action["domain"] = [("snapshot_id", "=", latest.id)]
            action["display_name"] = _("%s - %s") % (action.get("name"), latest.name)
        return action

    @api.model
    def action_open_main_funnel(self):
        latest = self.search([], order="snapshot_date desc, id desc", limit=1)
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "branch_supply_flow_dashboard.action_branch_supply_flow_funnel"
        )
        if latest:
            action["domain"] = [("snapshot_id", "=", latest.id)]
        return action

    @api.model
    def action_open_main_issues(self):
        latest = self.search([], order="snapshot_date desc, id desc", limit=1)
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "branch_supply_flow_dashboard.action_branch_supply_flow_issues"
        )
        if latest:
            action["domain"] = [
                ("snapshot_id", "=", latest.id),
                ("has_issue", "=", True),
            ]
        return action

    @api.model
    def action_open_main_transit_loss(self):
        latest = self.search([], order="snapshot_date desc, id desc", limit=1)
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "branch_supply_flow_dashboard.action_branch_supply_flow_transit_loss"
        )
        if latest:
            action["domain"] = [
                ("snapshot_id", "=", latest.id),
                ("has_transit_loss", "=", True),
            ]
        return action
