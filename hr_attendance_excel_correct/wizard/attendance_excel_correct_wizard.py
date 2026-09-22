# -*- coding: utf-8 -*-
import base64
import csv
import io
import logging
from datetime import datetime, date, time

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import openpyxl
except ImportError:
    openpyxl = None


ACTION_UPDATE = "update"
ACTION_CREATE = "create"
ACTION_SKIP = "skip"
ACTION_NO_CHANGE = "no_change"
ACTION_ERROR = "error"

APPLYABLE_ACTIONS = (ACTION_UPDATE, ACTION_CREATE)


class HrAttendanceExcelCorrectWizard(models.TransientModel):
    _name = "hr.attendance.excel.correct.wizard"
    _description = "Attendance Excel Correct Wizard"

    excel_file = fields.Binary(string="Excel / CSV File", required=True)
    file_name = fields.Char(string="File Name")
    company_id = fields.Many2one(
        "res.company",
        string="Limit to Company",
        help="If set, employees are matched only within this company.",
    )
    batch_size = fields.Integer(
        string="Batch Size",
        default=100,
        required=True,
        help="Number of rows applied per database commit.",
    )
    state = fields.Selection(
        [
            ("upload", "Upload"),
            ("preview", "Preview"),
            ("done", "Done"),
        ],
        default="upload",
        required=True,
    )
    line_ids = fields.One2many(
        "hr.attendance.excel.correct.line",
        "wizard_id",
        string="Preview Lines",
    )
    count_update = fields.Integer(compute="_compute_counts")
    count_create = fields.Integer(compute="_compute_counts")
    count_skip = fields.Integer(compute="_compute_counts")
    count_no_change = fields.Integer(compute="_compute_counts")
    count_error = fields.Integer(compute="_compute_counts")
    count_selected = fields.Integer(compute="_compute_counts")
    count_done = fields.Integer(compute="_compute_counts")
    result_message = fields.Text(readonly=True)

    @api.depends(
        "line_ids.action",
        "line_ids.apply",
        "line_ids.state",
    )
    def _compute_counts(self):
        for wizard in self:
            lines = wizard.line_ids
            wizard.count_update = len(lines.filtered(lambda l: l.action == ACTION_UPDATE))
            wizard.count_create = len(lines.filtered(lambda l: l.action == ACTION_CREATE))
            wizard.count_skip = len(lines.filtered(lambda l: l.action == ACTION_SKIP))
            wizard.count_no_change = len(lines.filtered(lambda l: l.action == ACTION_NO_CHANGE))
            wizard.count_error = len(lines.filtered(lambda l: l.action == ACTION_ERROR))
            wizard.count_selected = len(
                lines.filtered(lambda l: l.apply and l.action in APPLYABLE_ACTIONS and l.state == "pending")
            )
            wizard.count_done = len(lines.filtered(lambda l: l.state == "done"))

    # ------------------------------------------------------------------
    # File parsing
    # ------------------------------------------------------------------

    def _normalize_header(self, value):
        return str(value or "").strip().lower().replace(" ", "_")

    def _read_rows_from_file(self):
        """Return list of dicts keyed by normalized header names."""
        self.ensure_one()
        if not self.excel_file:
            raise UserError(_("Please upload an Excel or CSV file."))

        raw = base64.b64decode(self.excel_file)
        fname = (self.file_name or "").lower()

        if fname.endswith(".csv"):
            return self._read_csv_rows(raw)
        if fname.endswith(".xlsx") or fname.endswith(".xlsm"):
            return self._read_xlsx_rows(raw)
        # sniff
        if raw[:2] == b"PK":
            return self._read_xlsx_rows(raw)
        return self._read_csv_rows(raw)

    def _read_csv_rows(self, raw):
        text = raw.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise UserError(_("CSV file has no header row."))
        rows = []
        for row in reader:
            mapped = {self._normalize_header(k): v for k, v in row.items() if k is not None}
            if any(str(v or "").strip() for v in mapped.values()):
                rows.append(mapped)
        return rows

    def _read_xlsx_rows(self, raw):
        if not openpyxl:
            raise UserError(_(
                "The Python package 'openpyxl' is required to read Excel files. "
                "Install it on the server, or upload a CSV instead."
            ))
        try:
            wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
        except Exception as exc:
            raise UserError(_("Failed to read Excel file: %s") % exc) from exc

        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header = next(rows_iter)
        except StopIteration as exc:
            raise UserError(_("The Excel file is empty.")) from exc

        headers = [self._normalize_header(h) for h in header]
        rows = []
        for values in rows_iter:
            if not values or not any(v is not None and str(v).strip() for v in values):
                continue
            mapped = {}
            for idx, key in enumerate(headers):
                if not key:
                    continue
                mapped[key] = values[idx] if idx < len(values) else None
            rows.append(mapped)
        return rows

    def _cell(self, row, *keys):
        for key in keys:
            if key in row and row[key] not in (None, ""):
                return row[key]
        return None

    def _parse_date(self, value):
        if value in (None, ""):
            return False
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value).strip()
        if not text:
            return False
        # datetime string -> date part
        if " " in text:
            text = text.split(" ", 1)[0]
        if "T" in text:
            text = text.split("T", 1)[0]
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        raise ValueError(_("Invalid date: %s") % value)

    def _parse_datetime_utc(self, value):
        """Parse Excel value as naive UTC datetime (Odoo storage format)."""
        if value in (None, ""):
            return False
        if isinstance(value, datetime):
            # openpyxl may return naive local-looking values; treat as UTC as agreed
            return value.replace(microsecond=0, tzinfo=None)
        if isinstance(value, date) and not isinstance(value, datetime):
            return datetime.combine(value, time.min)
        text = str(value).strip()
        if not text or text.lower() in ("false", "none", "null"):
            return False
        text = text.replace("T", " ")
        if "+" in text[10:]:
            text = text.split("+", 1)[0].strip()
        if text.endswith("Z"):
            text = text[:-1].strip()
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        raise ValueError(_("Invalid datetime: %s") % value)

    def _normalize_code(self, value):
        if value in (None, ""):
            return ""
        text = str(value).strip()
        if text.endswith(".0"):
            text = text[:-2]
        return text

    # ------------------------------------------------------------------
    # Employee / attendance matching
    # ------------------------------------------------------------------

    def _build_employee_indexes(self):
        domain = [("active", "in", [True, False])]
        if self.company_id:
            domain.append(("company_id", "=", self.company_id.id))
        employees = self.env["hr.employee"].sudo().search(domain)

        by_number = {}
        by_national = {}
        for emp in employees:
            number = self._normalize_code(getattr(emp, "employee_number", False) or "")
            if number:
                by_number.setdefault(number, self.env["hr.employee"])
                by_number[number] |= emp
                stripped = number.lstrip("0") or number
                if stripped != number:
                    by_number.setdefault(stripped, self.env["hr.employee"])
                    by_number[stripped] |= emp

            national = self._normalize_code(getattr(emp, "national_id", False) or "")
            if national:
                by_national.setdefault(national, self.env["hr.employee"])
                by_national[national] |= emp

        return employees, by_number, by_national

    def _match_employee(self, row, by_number, by_national):
        number = self._normalize_code(self._cell(row, "employee_number", "employee_code", "emp_code"))
        national = self._normalize_code(self._cell(row, "national_id", "identification_id", "id_number"))
        name = (self._cell(row, "employee_name", "name") or "")
        name = str(name).strip() if name else ""

        candidates = self.env["hr.employee"]
        match_via = ""

        if number:
            candidates = by_number.get(number) or by_number.get(number.lstrip("0") or number) or self.env["hr.employee"]
            if candidates:
                match_via = "employee_number"
        if not candidates and national:
            candidates = by_national.get(national) or self.env["hr.employee"]
            if candidates:
                match_via = "national_id"

        if not candidates:
            return self.env["hr.employee"], _(
                "Employee not found (number=%s, national_id=%s, name=%s)."
            ) % (number or "-", national or "-", name or "-")

        if len(candidates) > 1:
            return self.env["hr.employee"], _(
                "Multiple employees matched via %s: %s. Skipped."
            ) % (match_via, ", ".join("%s [#%s]" % (e.name, e.id) for e in candidates))

        return candidates, ""

    def _find_attendances_for_day(self, employee, day):
        return self.env["hr.attendance"].sudo().search([
            ("employee_id", "=", employee.id),
            ("date", "=", day),
        ], order="check_in asc")

    def _values_equal(self, left, right):
        if not left and not right:
            return True
        if bool(left) != bool(right):
            return False
        return fields.Datetime.to_datetime(left) == fields.Datetime.to_datetime(right)

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def action_load_preview(self):
        self.ensure_one()
        if self.batch_size < 1:
            raise UserError(_("Batch size must be at least 1."))

        rows = self._read_rows_from_file()
        if not rows:
            raise UserError(_("No data rows found in the file."))

        _employees, by_number, by_national = self._build_employee_indexes()
        Line = self.env["hr.attendance.excel.correct.line"]
        self.line_ids.unlink()

        vals_list = []
        for idx, row in enumerate(rows, start=2):
            note = ""
            action = ACTION_SKIP
            apply = False
            employee = self.env["hr.employee"]
            attendance = self.env["hr.attendance"]
            day = False
            new_in = False
            new_out = False
            old_in = False
            old_out = False

            try:
                day = self._parse_date(
                    self._cell(row, "date")
                    or self._cell(row, "check_in")
                )
                new_in = self._parse_datetime_utc(self._cell(row, "check_in", "checkin"))
                new_out = self._parse_datetime_utc(self._cell(row, "check_out", "checkout"))

                if not day and new_in:
                    day = new_in.date()
                if not new_in:
                    raise ValueError(_("check_in is required."))
                if new_out and new_out < new_in:
                    raise ValueError(_("check_out is earlier than check_in."))

                employee, err = self._match_employee(row, by_number, by_national)
                if err:
                    action = ACTION_SKIP
                    note = err
                else:
                    attendances = self._find_attendances_for_day(employee, day)
                    if len(attendances) > 1:
                        action = ACTION_SKIP
                        note = _(
                            "Multiple attendance records on %s for %s (IDs: %s). Skipped — resolve manually."
                        ) % (
                            day,
                            employee.name,
                            ", ".join(str(a.id) for a in attendances),
                        )
                    elif len(attendances) == 1:
                        attendance = attendances
                        old_in = attendance.check_in
                        old_out = attendance.check_out
                        if self._values_equal(old_in, new_in) and self._values_equal(old_out, new_out):
                            action = ACTION_NO_CHANGE
                            note = _("Already matches Excel values.")
                            apply = False
                        else:
                            action = ACTION_UPDATE
                            note = _("Will update existing attendance.")
                            apply = True
                    else:
                        action = ACTION_CREATE
                        note = _("No attendance on this date — will create a new record.")
                        apply = True
            except Exception as exc:
                action = ACTION_ERROR
                note = str(exc)
                apply = False

            vals_list.append({
                "wizard_id": self.id,
                "excel_row": idx,
                "employee_id": employee.id if employee else False,
                "employee_number": self._normalize_code(
                    self._cell(row, "employee_number", "employee_code", "emp_code")
                ) or (employee.employee_number if employee and "employee_number" in employee._fields else ""),
                "employee_name_excel": str(self._cell(row, "employee_name", "name") or "").strip(),
                "attendance_id": attendance.id if attendance else False,
                "date": day,
                "old_check_in": old_in,
                "old_check_out": old_out,
                "new_check_in": new_in,
                "new_check_out": new_out or False,
                "action": action,
                "apply": apply,
                "note": note,
                "state": "pending",
            })

        if vals_list:
            Line.create(vals_list)

        self.state = "preview"
        return self._reopen()

    # ------------------------------------------------------------------
    # Apply (batched)
    # ------------------------------------------------------------------

    def action_apply(self):
        self.ensure_one()
        if self.state != "preview":
            raise UserError(_("Load the preview before applying."))

        lines = self.line_ids.filtered(
            lambda l: l.apply and l.action in APPLYABLE_ACTIONS and l.state == "pending"
        ).sorted(key=lambda l: l.excel_row)
        if not lines:
            raise UserError(_("No selected rows to apply."))

        wizard_id = self.id
        line_ids = lines.ids
        selected_total = len(line_ids)
        batch_size = self.batch_size or 100
        updated = created = failed = 0
        Line = self.env["hr.attendance.excel.correct.line"]

        # Process in batches; commit after each batch so progress is kept
        for start in range(0, selected_total, batch_size):
            wizard = self.env[self._name].browse(wizard_id)
            batch = Line.browse(line_ids[start:start + batch_size]).exists()
            for line in batch:
                action_before = line.action
                try:
                    with self.env.cr.savepoint():
                        wizard._apply_line(line)
                    line.write({"state": "done"})
                    if action_before == ACTION_UPDATE:
                        updated += 1
                    elif action_before == ACTION_CREATE:
                        created += 1
                except Exception as exc:
                    failed += 1
                    line.write({
                        "state": "failed",
                        "action": ACTION_ERROR,
                        "note": ((line.note or "") + (" | " if line.note else "")
                                 + _("Apply failed: %s") % exc),
                    })
                    _logger.exception(
                        "Attendance excel correct failed for row %s employee %s",
                        line.excel_row,
                        line.employee_id.id,
                    )
            self.env.cr.commit()
            self.env.clear()

        wizard = self.env[self._name].browse(wizard_id)
        wizard.write({
            "state": "done",
            "result_message": _(
                "Apply finished.\n"
                "Updated: %(updated)s\n"
                "Created: %(created)s\n"
                "Failed: %(failed)s\n"
                "Selected originally: %(selected)s"
            ) % {
                "updated": updated,
                "created": created,
                "failed": failed,
                "selected": selected_total,
            },
        })
        return wizard._reopen()

    def _apply_line(self, line):
        """Write or create attendance; core write/create recomputes overtime & hours."""
        if not line.employee_id:
            raise UserError(_("Missing employee."))
        if not line.new_check_in:
            raise UserError(_("Missing check_in."))

        Attendance = self.env["hr.attendance"].sudo()
        vals = {
            "check_in": line.new_check_in,
            "check_out": line.new_check_out or False,
        }

        if line.action == ACTION_UPDATE:
            if not line.attendance_id:
                raise UserError(_("Missing attendance to update."))
            # Re-check ambiguity just before write
            same_day = self._find_attendances_for_day(line.employee_id, line.date)
            if len(same_day) > 1:
                raise UserError(_(
                    "Multiple attendances now exist on %s (IDs: %s)."
                ) % (line.date, ", ".join(str(a.id) for a in same_day)))
            line.attendance_id.write(vals)
            # Neighbor overtime already handled inside hr.attendance.write via _update_overtime
            line.note = _("Updated attendance #%s. Worked hours / overtime recomputed.") % line.attendance_id.id
            return line.attendance_id

        if line.action == ACTION_CREATE:
            existing = self._find_attendances_for_day(line.employee_id, line.date)
            if existing:
                raise UserError(_(
                    "Attendance appeared on %s before create (IDs: %s). Skipped create."
                ) % (line.date, ", ".join(str(a.id) for a in existing)))
            create_vals = {
                "employee_id": line.employee_id.id,
                "check_in": line.new_check_in,
                "check_out": line.new_check_out or False,
            }
            attendance = Attendance.create(create_vals)
            line.attendance_id = attendance.id
            line.note = _("Created attendance #%s. Worked hours / overtime recomputed.") % attendance.id
            return attendance

        raise UserError(_("Unsupported action: %s") % line.action)

    def action_select_applyable(self):
        self.ensure_one()
        self.line_ids.filtered(lambda l: l.action in APPLYABLE_ACTIONS).write({"apply": True})
        return self._reopen()

    def action_unselect_all(self):
        self.ensure_one()
        self.line_ids.write({"apply": False})
        return self._reopen()

    def action_back_to_upload(self):
        self.ensure_one()
        self.line_ids.unlink()
        self.state = "upload"
        self.result_message = False
        return self._reopen()

    def _reopen(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }


class HrAttendanceExcelCorrectLine(models.TransientModel):
    _name = "hr.attendance.excel.correct.line"
    _description = "Attendance Excel Correct Preview Line"
    _order = "excel_row"

    wizard_id = fields.Many2one(
        "hr.attendance.excel.correct.wizard",
        required=True,
        ondelete="cascade",
    )
    excel_row = fields.Integer(string="Excel Row", readonly=True)
    employee_id = fields.Many2one("hr.employee", string="Employee", readonly=True)
    employee_number = fields.Char(string="Employee Number", readonly=True)
    employee_name_excel = fields.Char(string="Name (Excel)", readonly=True)
    company_id = fields.Many2one(
        related="employee_id.company_id",
        string="Company",
        readonly=True,
    )
    attendance_id = fields.Many2one("hr.attendance", string="Attendance", readonly=True)
    date = fields.Date(string="Date", readonly=True)
    old_check_in = fields.Datetime(string="Current Check In", readonly=True)
    old_check_out = fields.Datetime(string="Current Check Out", readonly=True)
    new_check_in = fields.Datetime(string="New Check In (UTC)", readonly=True)
    new_check_out = fields.Datetime(string="New Check Out (UTC)", readonly=True)
    action = fields.Selection(
        [
            (ACTION_UPDATE, "Update"),
            (ACTION_CREATE, "Create"),
            (ACTION_SKIP, "Skip"),
            (ACTION_NO_CHANGE, "No Change"),
            (ACTION_ERROR, "Error"),
        ],
        string="Action",
        readonly=True,
        required=True,
    )
    apply = fields.Boolean(
        string="Apply",
        help="Uncheck to exclude this row from the batch apply.",
    )
    note = fields.Char(string="Note", readonly=True)
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("done", "Done"),
            ("failed", "Failed"),
        ],
        default="pending",
        readonly=True,
    )
