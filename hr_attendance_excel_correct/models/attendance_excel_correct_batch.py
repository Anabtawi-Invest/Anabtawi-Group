# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


ACTION_SELECTION = [
    ("update", "Update"),
    ("create", "Create"),
    ("skip", "Skip"),
    ("no_change", "No Change"),
    ("error", "Error"),
    ("excluded", "Excluded"),
]

LINE_STATE_SELECTION = [
    ("pending", "Pending"),
    ("done", "Done"),
    ("failed", "Failed"),
    ("skipped", "Skipped"),
]

BATCH_STATE_SELECTION = [
    ("preview", "Preview"),
    ("partial", "Partially Applied"),
    ("done", "Done"),
    ("cancelled", "Cancelled"),
]


class HrAttendanceExcelCorrectBatch(models.Model):
    _name = "hr.attendance.excel.correct.batch"
    _description = "Attendance Excel Correct Batch"
    _order = "id desc"

    name = fields.Char(required=True, copy=False, default=lambda self: _("New"))
    file_name = fields.Char(string="File Name", readonly=True)
    company_id = fields.Many2one("res.company", string="Company Filter", readonly=True)
    user_id = fields.Many2one(
        "res.users",
        string="Imported By",
        default=lambda self: self.env.user,
        readonly=True,
        required=True,
    )
    batch_size = fields.Integer(readonly=True)
    state = fields.Selection(
        BATCH_STATE_SELECTION,
        default="preview",
        required=True,
        index=True,
    )
    line_ids = fields.One2many(
        "hr.attendance.excel.correct.log",
        "batch_id",
        string="Lines",
    )
    date_start = fields.Datetime(string="Started On", readonly=True)
    date_end = fields.Datetime(string="Finished On", readonly=True)
    result_message = fields.Text(string="Result", readonly=True)

    count_total = fields.Integer(compute="_compute_counts", store=True)
    count_update = fields.Integer(compute="_compute_counts", store=True)
    count_create = fields.Integer(compute="_compute_counts", store=True)
    count_skip = fields.Integer(compute="_compute_counts", store=True)
    count_no_change = fields.Integer(compute="_compute_counts", store=True)
    count_error = fields.Integer(compute="_compute_counts", store=True)
    count_done = fields.Integer(compute="_compute_counts", store=True)
    count_failed = fields.Integer(compute="_compute_counts", store=True)
    count_pending = fields.Integer(compute="_compute_counts", store=True)

    @api.depends(
        "line_ids",
        "line_ids.action",
        "line_ids.state",
    )
    def _compute_counts(self):
        for batch in self:
            lines = batch.line_ids
            batch.count_total = len(lines)
            batch.count_update = len(lines.filtered(lambda l: l.action == "update"))
            batch.count_create = len(lines.filtered(lambda l: l.action == "create"))
            batch.count_skip = len(lines.filtered(lambda l: l.action == "skip"))
            batch.count_no_change = len(lines.filtered(lambda l: l.action == "no_change"))
            batch.count_error = len(lines.filtered(lambda l: l.action == "error"))
            batch.count_done = len(lines.filtered(lambda l: l.state == "done"))
            batch.count_failed = len(lines.filtered(lambda l: l.state == "failed"))
            batch.count_pending = len(lines.filtered(lambda l: l.state == "pending"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "hr.attendance.excel.correct.batch"
                ) or _("ATT-XLS/%s") % fields.Datetime.now()
            vals.setdefault("date_start", fields.Datetime.now())
        return super().create(vals_list)

    def action_open_lines(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Batch Lines — %s") % self.name,
            "res_model": "hr.attendance.excel.correct.log",
            "view_mode": "list,form",
            "domain": [("batch_id", "=", self.id)],
            "context": {"default_batch_id": self.id, "search_default_group_state": 1},
        }


class HrAttendanceExcelCorrectLog(models.Model):
    _name = "hr.attendance.excel.correct.log"
    _description = "Attendance Excel Correct Log Line"
    _order = "batch_id desc, excel_row"

    batch_id = fields.Many2one(
        "hr.attendance.excel.correct.batch",
        string="Batch",
        required=True,
        ondelete="cascade",
        index=True,
    )
    excel_row = fields.Integer(string="Excel Row", index=True)
    employee_id = fields.Many2one("hr.employee", string="Employee", index=True)
    employee_number = fields.Char(string="Employee Number", index=True)
    employee_name_excel = fields.Char(string="Name (Excel)")
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="employee_id.company_id",
        store=True,
        index=True,
    )
    attendance_id = fields.Many2one("hr.attendance", string="Attendance", index=True)
    date = fields.Date(string="Date", index=True)
    old_check_in = fields.Datetime(string="Old Check In")
    old_check_out = fields.Datetime(string="Old Check Out")
    new_check_in = fields.Datetime(string="New Check In (UTC)")
    new_check_out = fields.Datetime(string="New Check Out (UTC)")
    action = fields.Selection(ACTION_SELECTION, string="Planned Action", required=True, index=True)
    state = fields.Selection(
        LINE_STATE_SELECTION,
        string="Status",
        default="pending",
        required=True,
        index=True,
    )
    note = fields.Text(string="Note")
    apply_requested = fields.Boolean(
        string="Was Selected to Apply",
        help="True if the user selected this row when applying the wizard.",
    )
    applied_date = fields.Datetime(string="Applied On", readonly=True)
    user_id = fields.Many2one(
        related="batch_id.user_id",
        string="Imported By",
        store=True,
        index=True,
    )
    batch_state = fields.Selection(
        related="batch_id.state",
        string="Batch Status",
        store=True,
    )

    def action_open_attendance(self):
        self.ensure_one()
        if not self.attendance_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "hr.attendance",
            "res_id": self.attendance_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_employee(self):
        self.ensure_one()
        if not self.employee_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "hr.employee",
            "res_id": self.employee_id.id,
            "view_mode": "form",
            "target": "current",
        }
