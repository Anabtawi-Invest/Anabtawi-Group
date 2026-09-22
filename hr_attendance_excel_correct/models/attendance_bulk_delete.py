# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HrAttendanceExcelDeleteJob(models.Model):
    _name = "hr.attendance.excel.delete.job"
    _description = "Attendance Bulk Delete Job"
    _order = "id desc"

    name = fields.Char(required=True, copy=False, default=lambda self: _("New"))
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    company_id = fields.Many2one("res.company", string="Company")
    batch_size = fields.Integer(default=500, required=True)
    user_id = fields.Many2one(
        "res.users",
        default=lambda self: self.env.user,
        required=True,
        readonly=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("running", "Running"),
            ("done", "Done"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        index=True,
    )
    count_total = fields.Integer(readonly=True)
    count_deleted = fields.Integer(readonly=True)
    count_ot_deleted = fields.Integer(string="Overtime Lines Deleted", readonly=True)
    count_remaining = fields.Integer(readonly=True)
    result_message = fields.Text(readonly=True)
    date_start = fields.Datetime(readonly=True)
    date_end = fields.Datetime(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "hr.attendance.excel.delete.job"
                ) or _("DEL-ATT/%s") % fields.Datetime.now()
        return super().create(vals_list)

    def _attendance_domain(self):
        self.ensure_one()
        domain = [
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
        ]
        if self.company_id:
            domain.append(("employee_id.company_id", "=", self.company_id.id))
        return domain

    def _overtime_domain(self):
        self.ensure_one()
        domain = [
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
        ]
        if self.company_id:
            domain.append(("employee_id.company_id", "=", self.company_id.id))
        return domain

    def action_refresh(self):
        self.ensure_one()
        if self.state == "running":
            self._process_chunk()
            if self.state == "running":
                self._trigger_cron()
        return {
            "type": "ir.actions.act_window",
            "name": _("Bulk Delete Job"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }

    def action_cancel(self):
        self.ensure_one()
        if self.state != "running":
            raise UserError(_("Only a running job can be cancelled."))
        self.write({
            "state": "cancelled",
            "date_end": fields.Datetime.now(),
            "result_message": _(
                "Cancelled by user after deleting %s attendance(s). "
                "Remaining records were left in place."
            ) % self.count_deleted,
        })
        return self.action_refresh()

    def action_start(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_("Date From must be before Date To."))
        if self.batch_size < 1:
            raise UserError(_("Batch size must be at least 1."))

        Attendance = self.env["hr.attendance"].sudo()
        total = Attendance.search_count(self._attendance_domain())
        if not total:
            raise UserError(_("No attendance records found for this period."))

        # Delete overtime lines once up-front (much cheaper than per attendance unlink)
        ot_deleted = 0
        if "hr.attendance.overtime.line" in self.env:
            OT = self.env["hr.attendance.overtime.line"].sudo()
            ot_lines = OT.search(self._overtime_domain())
            ot_deleted = len(ot_lines)
            while ot_lines:
                chunk = ot_lines[:1000]
                ot_lines = ot_lines[1000:]
                chunk.unlink()

        self.write({
            "state": "running",
            "count_total": total,
            "count_deleted": 0,
            "count_ot_deleted": ot_deleted,
            "count_remaining": total,
            "date_start": fields.Datetime.now(),
            "date_end": False,
            "result_message": _(
                "Bulk delete started. Overtime lines removed: %s. "
                "Deleting attendances in the background…"
            ) % ot_deleted,
        })
        self._trigger_cron()
        # Process first chunk immediately so user sees progress
        self._process_chunk()
        return self.action_refresh()

    def _trigger_cron(self):
        cron = self.env.ref(
            "hr_attendance_excel_correct.ir_cron_attendance_excel_bulk_delete",
            raise_if_not_found=False,
        )
        if cron:
            try:
                cron.sudo()._trigger()
            except Exception:
                _logger.exception("Failed to trigger attendance bulk delete cron")

    def _process_chunk(self):
        self.ensure_one()
        if self.state != "running":
            return False

        Attendance = self.env["hr.attendance"].sudo().with_context(
            hr_attendance_excel_bulk_delete=True,
            tracking_disable=True,
            mail_notrack=True,
            mail_create_nolog=True,
        )
        limit = self.batch_size or 500
        chunk = Attendance.search(self._attendance_domain(), limit=limit, order="id")
        if not chunk:
            self.write({
                "state": "done",
                "count_remaining": 0,
                "date_end": fields.Datetime.now(),
                "result_message": _(
                    "Bulk delete finished.\n"
                    "Attendances deleted: %(deleted)s / %(total)s\n"
                    "Overtime lines deleted: %(ot)s\n"
                    "You can now run Correct Attendance from Excel to recreate."
                ) % {
                    "deleted": self.count_deleted,
                    "total": self.count_total,
                    "ot": self.count_ot_deleted,
                },
            })
            return False

        deleted_now = len(chunk)
        chunk.unlink()
        remaining = Attendance.search_count(self._attendance_domain())
        new_deleted = self.count_deleted + deleted_now
        vals = {
            "count_deleted": new_deleted,
            "count_remaining": remaining,
            "result_message": _(
                "Bulk delete in progress…\n"
                "Deleted: %(deleted)s / %(total)s\n"
                "Remaining: %(remaining)s"
            ) % {
                "deleted": new_deleted,
                "total": self.count_total,
                "remaining": remaining,
            },
        }
        if remaining:
            self.write(vals)
            return True
        vals.update({
            "state": "done",
            "count_remaining": 0,
            "date_end": fields.Datetime.now(),
            "result_message": _(
                "Bulk delete finished.\n"
                "Attendances deleted: %(deleted)s\n"
                "Overtime lines deleted: %(ot)s\n"
                "You can now run Correct Attendance from Excel to recreate."
            ) % {
                "deleted": new_deleted,
                "ot": self.count_ot_deleted,
            },
        })
        self.write(vals)
        return False

    @api.model
    def _cron_process_bulk_delete_jobs(self):
        jobs = self.search([("state", "=", "running")], order="id")
        more = False
        for job in jobs:
            try:
                if job._process_chunk():
                    more = True
            except Exception:
                _logger.exception("Bulk delete job %s failed", job.id)
                job.write({
                    "result_message": _(
                        "Error during bulk delete — check server logs. Job stays Running; use Refresh to retry."
                    ),
                })
                more = True
        if more:
            cron = self.env.ref(
                "hr_attendance_excel_correct.ir_cron_attendance_excel_bulk_delete",
                raise_if_not_found=False,
            )
            if cron:
                try:
                    cron.sudo()._trigger()
                except Exception:
                    _logger.exception("Failed to re-trigger bulk delete cron")


class HrAttendanceExcelBulkDeleteWizard(models.TransientModel):
    _name = "hr.attendance.excel.bulk.delete.wizard"
    _description = "Attendance Bulk Delete Wizard"

    date_from = fields.Date(required=True, default=lambda self: fields.Date.to_date("2026-09-01"))
    date_to = fields.Date(required=True, default=lambda self: fields.Date.to_date("2026-09-21"))
    company_id = fields.Many2one("res.company", string="Limit to Company")
    batch_size = fields.Integer(default=500, required=True)
    matched_count = fields.Integer(string="Attendances to Delete", readonly=True)
    overtime_count = fields.Integer(string="Overtime Lines to Delete", readonly=True)

    @api.onchange("date_from", "date_to", "company_id")
    def _onchange_count(self):
        for wiz in self:
            wiz.matched_count = 0
            wiz.overtime_count = 0
            if not wiz.date_from or not wiz.date_to or wiz.date_from > wiz.date_to:
                continue
            domain = [
                ("date", ">=", wiz.date_from),
                ("date", "<=", wiz.date_to),
            ]
            if wiz.company_id:
                domain.append(("employee_id.company_id", "=", wiz.company_id.id))
            wiz.matched_count = self.env["hr.attendance"].sudo().search_count(domain)
            if "hr.attendance.overtime.line" in self.env:
                wiz.overtime_count = self.env["hr.attendance.overtime.line"].sudo().search_count(domain)

    def action_start_delete(self):
        self.ensure_one()
        if not self.matched_count:
            self._onchange_count()
        if not self.matched_count:
            raise UserError(_("No attendance records found for this period."))

        job = self.env["hr.attendance.excel.delete.job"].create({
            "date_from": self.date_from,
            "date_to": self.date_to,
            "company_id": self.company_id.id if self.company_id else False,
            "batch_size": self.batch_size or 500,
        })
        return job.action_start()
