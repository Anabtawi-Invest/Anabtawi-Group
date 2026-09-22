# -*- coding: utf-8 -*-
import json
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
    reset_work_entries = fields.Boolean(
        string="Reset Validated Work Entries",
        default=True,
        help="Set linked validated work entries back to draft so attendances can be deleted. "
             "Entries already used on a payslip stay locked and those attendances are skipped.",
    )
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
    count_we_reset = fields.Integer(string="Work Entries Reset to Draft", readonly=True)
    count_locked = fields.Integer(
        string="Locked (Payslip)",
        readonly=True,
        help="Attendances that could not be deleted because work entries are on a payslip.",
    )
    count_remaining = fields.Integer(readonly=True)
    locked_attendance_ids_json = fields.Text(default="[]", readonly=True)
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

    def _locked_ids(self):
        self.ensure_one()
        try:
            return set(json.loads(self.locked_attendance_ids_json or "[]"))
        except Exception:
            return set()

    def _attendance_domain(self):
        self.ensure_one()
        domain = [
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
        ]
        if self.company_id:
            domain.append(("employee_id.company_id", "=", self.company_id.id))
        locked = list(self._locked_ids())
        if locked:
            domain.append(("id", "not in", locked))
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

    def _prepare_attendances_for_delete(self, attendances):
        """
        Reset validated work entries to draft when possible.
        Return (deletable_attendances, locked_attendances, we_reset_count).
        """
        self.ensure_one()
        if not attendances or "hr.work.entry" not in self.env:
            return attendances, attendances.browse(), 0

        WE = self.env["hr.work.entry"].sudo()
        validated = WE.search([
            ("attendance_id", "in", attendances.ids),
            ("state", "=", "validated"),
        ])
        if not validated:
            return attendances, attendances.browse(), 0

        if not self.reset_work_entries:
            locked = attendances.filtered(
                lambda a: a.id in validated.mapped("attendance_id").ids
            )
            return attendances - locked, locked, 0

        locked_att_ids = set()
        to_draft = WE.browse()
        for we in validated:
            # Payslip-linked validated entries cannot be moved to draft
            if "has_payslip" in we._fields and we.has_payslip:
                if we.attendance_id:
                    locked_att_ids.add(we.attendance_id.id)
                continue
            to_draft |= we

        we_reset = 0
        if to_draft:
            # Prefer official method when available
            if hasattr(to_draft, "action_set_to_draft"):
                to_draft.action_set_to_draft()
            else:
                to_draft.write({"state": "draft"})
            we_reset = len(to_draft)

        locked = attendances.filtered(lambda a: a.id in locked_att_ids)
        return attendances - locked, locked, we_reset

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
            "count_we_reset": 0,
            "count_locked": 0,
            "count_remaining": total,
            "locked_attendance_ids_json": "[]",
            "date_start": fields.Datetime.now(),
            "date_end": False,
            "result_message": _(
                "Bulk delete started. Overtime lines removed: %s. "
                "Validated work entries will be reset to draft when possible…"
            ) % ot_deleted,
        })
        self._trigger_cron()
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
                    "Work entries reset to draft: %(we)s\n"
                    "Locked by payslip (skipped): %(locked)s\n"
                    "You can now run Correct Attendance from Excel to recreate."
                ) % {
                    "deleted": self.count_deleted,
                    "total": self.count_total,
                    "ot": self.count_ot_deleted,
                    "we": self.count_we_reset,
                    "locked": self.count_locked,
                },
            })
            return False

        deletable, locked, we_reset = self._prepare_attendances_for_delete(chunk)
        locked_ids = self._locked_ids()
        if locked:
            locked_ids |= set(locked.ids)

        deleted_now = 0
        if deletable:
            deleted_now = len(deletable)
            deletable.unlink()

        # Persist locked ids so next search skips them (avoid infinite loop)
        remaining = Attendance.search_count(self._attendance_domain())
        # After updating locked json, recompute remaining excluding new locked
        new_locked_json = json.dumps(sorted(locked_ids))
        self.write({"locked_attendance_ids_json": new_locked_json})
        remaining = Attendance.search_count(self._attendance_domain())

        new_deleted = self.count_deleted + deleted_now
        new_locked = len(locked_ids)
        new_we = self.count_we_reset + we_reset
        vals = {
            "count_deleted": new_deleted,
            "count_locked": new_locked,
            "count_we_reset": new_we,
            "count_remaining": remaining,
            "result_message": _(
                "Bulk delete in progress…\n"
                "Deleted: %(deleted)s / %(total)s\n"
                "Remaining: %(remaining)s\n"
                "Work entries reset: %(we)s\n"
                "Locked by payslip: %(locked)s"
            ) % {
                "deleted": new_deleted,
                "total": self.count_total,
                "remaining": remaining,
                "we": new_we,
                "locked": new_locked,
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
                "Work entries reset to draft: %(we)s\n"
                "Locked by payslip (skipped): %(locked)s\n"
                "You can now run Correct Attendance from Excel to recreate."
            ) % {
                "deleted": new_deleted,
                "ot": self.count_ot_deleted,
                "we": new_we,
                "locked": new_locked,
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
            except Exception as exc:
                _logger.exception("Bulk delete job %s failed", job.id)
                job.write({
                    "result_message": _(
                        "Error during bulk delete: %s\n"
                        "Job stays Running; use Refresh to retry."
                    ) % exc,
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
    reset_work_entries = fields.Boolean(
        string="Reset Validated Work Entries to Draft",
        default=True,
        help="Required when attendances are linked to validated work entries. "
             "Entries already on a payslip cannot be reset and those attendances are skipped.",
    )
    matched_count = fields.Integer(string="Attendances to Delete", readonly=True)
    overtime_count = fields.Integer(string="Overtime Lines to Delete", readonly=True)
    validated_we_count = fields.Integer(string="Validated Work Entries Linked", readonly=True)

    @api.onchange("date_from", "date_to", "company_id")
    def _onchange_count(self):
        for wiz in self:
            wiz.matched_count = 0
            wiz.overtime_count = 0
            wiz.validated_we_count = 0
            if not wiz.date_from or not wiz.date_to or wiz.date_from > wiz.date_to:
                continue
            domain = [
                ("date", ">=", wiz.date_from),
                ("date", "<=", wiz.date_to),
            ]
            if wiz.company_id:
                domain.append(("employee_id.company_id", "=", wiz.company_id.id))
            atts = self.env["hr.attendance"].sudo().search(domain)
            wiz.matched_count = len(atts)
            if "hr.attendance.overtime.line" in self.env:
                wiz.overtime_count = self.env["hr.attendance.overtime.line"].sudo().search_count(domain)
            if atts and "hr.work.entry" in self.env:
                wiz.validated_we_count = self.env["hr.work.entry"].sudo().search_count([
                    ("attendance_id", "in", atts.ids),
                    ("state", "=", "validated"),
                ])

    def action_start_delete(self):
        self.ensure_one()
        if not self.matched_count:
            self._onchange_count()
        if not self.matched_count:
            raise UserError(_("No attendance records found for this period."))
        if self.validated_we_count and not self.reset_work_entries:
            raise UserError(_(
                "There are %s validated work entries linked to these attendances. "
                "Enable 'Reset Validated Work Entries to Draft' (or reset them manually in Payroll)."
            ) % self.validated_we_count)

        job = self.env["hr.attendance.excel.delete.job"].create({
            "date_from": self.date_from,
            "date_to": self.date_to,
            "company_id": self.company_id.id if self.company_id else False,
            "batch_size": self.batch_size or 500,
            "reset_work_entries": self.reset_work_entries,
        })
        return job.action_start()
