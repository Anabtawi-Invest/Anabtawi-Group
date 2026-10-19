# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


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
    ("queued", "Queued"),
    ("done", "Done"),
    ("failed", "Failed"),
    ("skipped", "Skipped"),
]

PROGRESS_STATUS_SELECTION = [
    ("not_yet", "Not yet"),
    ("created", "Created"),
    ("corrected", "Corrected"),
    ("failed", "Failed"),
    ("skipped", "Skipped"),
    ("no_change", "No change"),
]

BATCH_STATE_SELECTION = [
    ("preview", "Preview"),
    ("running", "Running (Background)"),
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
    batch_size = fields.Integer(readonly=True, default=100)
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
    count_queued = fields.Integer(compute="_compute_counts", store=True)
    count_created = fields.Integer(
        string="Created (done)",
        compute="_compute_counts",
        store=True,
        help="Lines successfully created.",
    )
    count_corrected = fields.Integer(
        string="Corrected (done)",
        compute="_compute_counts",
        store=True,
        help="Lines successfully updated/corrected.",
    )

    @api.depends(
        "line_ids",
        "line_ids.action",
        "line_ids.state",
        "line_ids.progress_status",
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
            batch.count_queued = len(lines.filtered(lambda l: l.state == "queued"))
            batch.count_created = len(lines.filtered(lambda l: l.progress_status == "created"))
            batch.count_corrected = len(lines.filtered(lambda l: l.progress_status == "corrected"))

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
            "views": [(False, "list"), (False, "form")],
            "domain": [("batch_id", "=", self.id)],
            "context": {
                "default_batch_id": self.id,
                "search_default_group_progress": 1,
            },
        }

    def action_refresh(self):
        """Refresh counts; if still running, process one chunk now so progress moves."""
        self.ensure_one()
        if self.state == "running":
            self._process_queued_chunk()
            if self.state == "running":
                self._trigger_background_cron()
        return {
            "type": "ir.actions.act_window",
            "name": _("Excel Import Batch"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }

    def action_skip_process(self):
        """Stop background apply: skip all remaining queued lines."""
        self.ensure_one()
        if self.state not in ("running", "preview", "partial"):
            raise UserError(_("Nothing to skip for this batch (state: %s).") % self.state)

        queued = self.line_ids.filtered(lambda l: l.state == "queued")
        pending_applyable = self.line_ids.filtered(
            lambda l: l.state == "pending" and l.action in ("update", "create")
        )
        to_skip = queued | pending_applyable
        if to_skip:
            to_skip.write({
                "state": "skipped",
                "apply_requested": False,
                "note": _("Skipped by user — process cancelled."),
            })

        done = self.line_ids.search_count([("batch_id", "=", self.id), ("state", "=", "done")])
        failed = self.line_ids.search_count([("batch_id", "=", self.id), ("state", "=", "failed")])
        self.write({
            "state": "cancelled",
            "date_end": fields.Datetime.now(),
            "result_message": _(
                "Process skipped/cancelled by user.\n"
                "Corrected/Created before cancel: %(done)s\n"
                "Failed: %(failed)s\n"
                "Skipped remaining: %(skipped)s"
            ) % {
                "done": done,
                "failed": failed,
                "skipped": len(to_skip),
            },
        })
        return self.action_refresh()

    def action_queue_selected_logs(self, log_ids):
        """Queue specific log lines for background apply and trigger the cron."""
        self.ensure_one()
        logs = self.env["hr.attendance.excel.correct.log"].browse(log_ids).filtered(
            lambda l: l.batch_id.id == self.id
            and l.action in ("update", "create")
            and l.state in ("pending", "queued", "failed")
        )
        if not logs:
            raise UserError(_("No applyable lines to queue."))

        # Exclude other pending applyable lines on this batch that were not selected
        other = self.line_ids.filtered(
            lambda l: l.id not in logs.ids
            and l.action in ("update", "create")
            and l.state == "pending"
        )
        if other:
            other.write({
                "state": "skipped",
                "action": "excluded",
                "note": _("Not selected for apply."),
                "apply_requested": False,
            })

        logs.write({
            "state": "queued",
            "apply_requested": True,
        })
        self.write({
            "state": "running",
            "date_end": False,
            "result_message": _(
                "Background apply started for %s line(s). "
                "Refresh this batch / Import Lines to follow progress."
            ) % len(logs),
        })
        self._trigger_background_cron()
        return True

    def _trigger_background_cron(self):
        cron = self.env.ref(
            "hr_attendance_excel_correct.ir_cron_attendance_excel_correct_apply",
            raise_if_not_found=False,
        )
        if cron:
            try:
                cron.sudo()._trigger()
            except Exception:
                _logger.exception("Failed to trigger attendance excel correct cron")

    def _find_attendances_for_day(self, employee, day):
        return self.env["hr.attendance"].sudo().search([
            ("employee_id", "=", employee.id),
            ("date", "=", day),
        ], order="check_in asc")

    def _apply_log_line(self, line):
        """Create/update hr.attendance for one tracking log line."""
        if not line.employee_id:
            raise UserError(_("Missing employee."))
        if not line.new_check_in:
            raise UserError(_("Missing check_in."))

        Attendance = self.env["hr.attendance"].sudo()
        vals = {
            "check_in": line.new_check_in,
            "check_out": line.new_check_out or False,
        }

        if line.action == "update":
            if not line.attendance_id:
                raise UserError(_("Missing attendance to update."))
            line.attendance_id.write(vals)
            note = _("Updated attendance #%s. Worked hours / overtime recomputed.") % line.attendance_id.id
            return line.attendance_id, note

        if line.action == "create":
            # Multi-session days are allowed: create an extra interval.
            # Overlap constraints on hr.attendance will still block invalid times.
            attendance = Attendance.create({
                "employee_id": line.employee_id.id,
                "check_in": line.new_check_in,
                "check_out": line.new_check_out or False,
            })
            note = _("Created attendance #%s. Worked hours / overtime recomputed.") % attendance.id
            return attendance, note

        raise UserError(_("Unsupported action: %s") % line.action)

    def _process_queued_chunk(self):
        """Process up to batch_size queued lines. Returns True if more remain."""
        self.ensure_one()
        limit = self.batch_size or 100
        lines = self.line_ids.search([
            ("batch_id", "=", self.id),
            ("state", "=", "queued"),
            ("apply_requested", "=", True),
            ("action", "in", ("update", "create")),
        ], order="excel_row", limit=limit)

        if not lines:
            self._finalize_if_idle()
            return False

        now = fields.Datetime.now()
        for line in lines:
            action_before = line.action
            try:
                with self.env.cr.savepoint():
                    attendance, note = self._apply_log_line(line)
                line.write({
                    "state": "done",
                    "action": action_before,
                    "attendance_id": attendance.id,
                    "note": note,
                    "applied_date": now,
                })
            except Exception as exc:
                note = ((line.note or "") + (" | " if line.note else "")
                        + _("Apply failed: %s") % exc)
                line.write({
                    "state": "failed",
                    "action": "error",
                    "note": note,
                    "applied_date": now,
                })
                _logger.exception(
                    "Background attendance excel correct failed batch=%s row=%s emp=%s",
                    self.id,
                    line.excel_row,
                    line.employee_id.id,
                )

        remaining = self.line_ids.search_count([
            ("batch_id", "=", self.id),
            ("state", "=", "queued"),
            ("apply_requested", "=", True),
        ])
        done = self.line_ids.search_count([("batch_id", "=", self.id), ("state", "=", "done")])
        failed = self.line_ids.search_count([("batch_id", "=", self.id), ("state", "=", "failed")])
        self.write({
            "result_message": _(
                "Background apply in progress…\n"
                "Done: %(done)s\n"
                "Failed: %(failed)s\n"
                "Queued left: %(queued)s"
            ) % {"done": done, "failed": failed, "queued": remaining},
        })
        if remaining:
            return True
        self._finalize_if_idle()
        return False

    def _finalize_if_idle(self):
        self.ensure_one()
        queued = self.line_ids.search_count([
            ("batch_id", "=", self.id),
            ("state", "=", "queued"),
        ])
        if queued:
            return
        pending = self.line_ids.search_count([
            ("batch_id", "=", self.id),
            ("state", "=", "pending"),
        ])
        done = self.line_ids.search_count([("batch_id", "=", self.id), ("state", "=", "done")])
        failed = self.line_ids.search_count([("batch_id", "=", self.id), ("state", "=", "failed")])
        self.write({
            "state": "partial" if pending else "done",
            "date_end": fields.Datetime.now(),
            "result_message": _(
                "Background apply finished.\n"
                "Done: %(done)s\n"
                "Failed: %(failed)s\n"
                "Pending left: %(pending)s"
            ) % {"done": done, "failed": failed, "pending": pending},
        })

    @api.model
    def _cron_process_excel_correct_batches(self):
        """Cron: process every running batch one chunk; re-trigger if work remains."""
        batches = self.search([("state", "=", "running")], order="id")
        more_work = False
        for batch in batches:
            try:
                if batch._process_queued_chunk():
                    more_work = True
            except Exception:
                _logger.exception("Cron failed on attendance excel batch %s", batch.id)
                batch.write({
                    "result_message": _(
                        "Background job error — check server logs. Batch stays Running; cron will retry."
                    ),
                })
                more_work = True
        if more_work:
            self._trigger_background_cron_static()

    @api.model
    def _trigger_background_cron_static(self):
        cron = self.env.ref(
            "hr_attendance_excel_correct.ir_cron_attendance_excel_correct_apply",
            raise_if_not_found=False,
        )
        if cron:
            try:
                cron.sudo()._trigger()
            except Exception:
                _logger.exception("Failed to re-trigger attendance excel correct cron")


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
        string="Technical Status",
        default="pending",
        required=True,
        index=True,
    )
    progress_status = fields.Selection(
        PROGRESS_STATUS_SELECTION,
        string="Status",
        compute="_compute_progress_status",
        store=True,
        index=True,
        help="Created / Corrected / Not yet / Failed / Skipped",
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

    @api.depends("state", "action")
    def _compute_progress_status(self):
        for line in self:
            if line.state == "done":
                if line.action == "create":
                    line.progress_status = "created"
                elif line.action == "update":
                    line.progress_status = "corrected"
                else:
                    line.progress_status = "corrected"
            elif line.state == "failed" or line.action == "error":
                line.progress_status = "failed"
            elif line.action == "no_change":
                line.progress_status = "no_change"
            elif line.state == "skipped" or line.action in ("skip", "excluded"):
                line.progress_status = "skipped"
            else:
                # pending / queued applyable rows
                line.progress_status = "not_yet"

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
