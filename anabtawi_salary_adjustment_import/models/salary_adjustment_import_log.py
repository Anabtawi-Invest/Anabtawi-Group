import logging
import time

from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..tools import normalize

_logger = logging.getLogger(__name__)

BATCH_SIZE = 100
TIME_BUDGET_SECONDS = 120

DURATION_SELECTION = [("one", "One Time"), ("limited", "Limited"), ("unlimited", "Unlimited")]


class SalaryAdjustmentImportLog(models.Model):
    _name = "salary.adjustment.import.log"
    _inherit = ["mail.thread"]
    _description = "Salary Adjustments Import Log"
    _order = "create_date desc, id desc"

    name = fields.Char(required=True, readonly=True, copy=False, default=lambda self: _("New"))
    user_id = fields.Many2one("res.users", string="Imported By", default=lambda self: self.env.user, readonly=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, readonly=True)
    allowed_company_ids = fields.Many2many(
        "res.company", string="Allowed Companies", readonly=True,
        default=lambda self: self.env.companies,
    )
    mode = fields.Selection(
        [("review", "After Review"), ("direct", "Direct (no review)")],
        string="Import Mode", readonly=True,
    )
    one_time = fields.Boolean(string="One Time", readonly=True)
    file = fields.Binary(string="Imported File", readonly=True, attachment=True)
    file_name = fields.Char(readonly=True)
    line_ids = fields.One2many("salary.adjustment.import.log.line", "log_id", string="Rows", readonly=True)
    state = fields.Selection(
        [
            ("queued", "Queued"),
            ("in_progress", "In Progress"),
            ("done", "Done"),
            ("partial", "Partially Done"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
        ],
        string="Status", default="queued", required=True, readonly=True, tracking=True,
    )
    date_started = fields.Datetime(string="Started On", readonly=True)
    date_finished = fields.Datetime(string="Finished On", readonly=True)
    total_count = fields.Integer(string="Rows", compute="_compute_counts", store=True)
    imported_count = fields.Integer(string="Imported", compute="_compute_counts", store=True)
    failed_count = fields.Integer(string="Failed", compute="_compute_counts", store=True)
    pending_count = fields.Integer(string="Pending", compute="_compute_counts", store=True)
    progress = fields.Float(string="Progress", compute="_compute_counts", store=True)

    @api.depends("line_ids.status")
    def _compute_counts(self):
        for log in self:
            statuses = log.line_ids.mapped("status")
            log.total_count = len(statuses)
            log.imported_count = statuses.count("imported")
            log.failed_count = statuses.count("failed")
            log.pending_count = statuses.count("pending")
            processed = log.total_count - log.pending_count
            log.progress = (processed / log.total_count * 100) if log.total_count else 100.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("salary.adjustment.import.log") or _("New")
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    def action_refresh(self):
        return True

    def action_view_adjustments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Imported Salary Adjustments"),
            "res_model": "hr.salary.attachment",
            "view_mode": "list,form",
            "domain": [("id", "in", self.line_ids.adjustment_id.ids)],
        }

    def action_cancel(self):
        for log in self:
            if log.state not in ("queued", "in_progress"):
                raise UserError(_("Only queued or in-progress imports can be cancelled."))
            log.line_ids.filtered(lambda l: l.status == "pending").write({"status": "cancelled"})
            log.write({"state": "cancelled", "date_finished": fields.Datetime.now()})
            log.message_post(body=_("Import cancelled by %s.", self.env.user.name))

    def action_retry_failed(self):
        for log in self:
            if log.state in ("queued", "in_progress"):
                raise UserError(_("This import is still running."))
            lines = log.line_ids.filtered(lambda l: l.status in ("failed", "cancelled"))
            if not lines:
                raise UserError(_("There are no failed rows to retry."))
            lines.write({"status": "pending", "message": False})
            log.write({"state": "queued", "date_finished": False})
            log.message_post(body=_("%s row(s) queued again by %s.", len(lines), self.env.user.name))
        self._trigger_processing()
        return True

    # ------------------------------------------------------------------
    # Background processing
    # ------------------------------------------------------------------

    def _trigger_processing(self):
        self.env.ref("anabtawi_salary_adjustment_import.ir_cron_process_salary_adjustment_import")._trigger()

    @api.model
    def _cron_process_imports(self):
        started = time.monotonic()
        for log in self.search([("state", "in", ("queued", "in_progress"))], order="id"):
            if not log._process_pending(started):
                self._trigger_processing()
                return

    def _process_pending(self, started):
        """Process pending rows in committed batches. Return False when the time budget is exhausted."""
        self.ensure_one()
        if self.state == "queued":
            self.write({"state": "in_progress", "date_started": fields.Datetime.now()})
            self.env.cr.commit()

        log = self.with_user(self.user_id).with_context(
            allowed_company_ids=(self.allowed_company_ids or self.company_id).ids,
            tracking_disable=True,
        )
        lookups = log._build_lookups()
        Line = log.env["salary.adjustment.import.log.line"]
        while True:
            self.invalidate_recordset(["state"])
            if self.state != "in_progress":
                return True
            lines = Line.search(
                [("log_id", "=", self.id), ("status", "=", "pending")], order="row_number", limit=BATCH_SIZE,
            )
            if not lines:
                self._finish()
                self.env.cr.commit()
                return True
            for line in lines:
                line._process(lookups)
            self.env.cr.commit()
            if time.monotonic() - started > TIME_BUDGET_SECONDS:
                return False

    def _build_lookups(self):
        employees_by_name = {}
        employees = self.env["hr.employee"].search([("company_id", "in", self.env.companies.ids)])
        for employee in employees:
            key = normalize(employee.name)
            employees_by_name[key] = employees_by_name.get(key, self.env["hr.employee"]) | employee

        types_by_name = {}
        for input_type in self.env["hr.payslip.input.type"].search([("available_in_attachments", "=", True)]):
            for name in (input_type.name, input_type.with_context(lang="en_US").name, input_type.code):
                if name:
                    types_by_name.setdefault(normalize(name), input_type)
        return employees_by_name, types_by_name

    def _finish(self):
        self.ensure_one()
        if not self.failed_count:
            state = "done"
        elif self.imported_count:
            state = "partial"
        else:
            state = "failed"
        self.write({"state": state, "date_finished": fields.Datetime.now()})

        message = _(
            "Import %(name)s finished: %(imported)s imported, %(failed)s failed out of %(total)s rows.",
            name=self.name, imported=self.imported_count, failed=self.failed_count, total=self.total_count,
        )
        self.message_post(body=Markup("<p>%s</p>") % message, partner_ids=self.user_id.partner_id.ids)
        self.user_id._bus_send("simple_notification", {
            "type": "success" if state == "done" else "warning",
            "title": _("Salary Adjustments Import"),
            "message": message,
            "sticky": state != "done",
        })


class SalaryAdjustmentImportLogLine(models.Model):
    _name = "salary.adjustment.import.log.line"
    _description = "Salary Adjustments Import Log Line"
    _order = "log_id desc, row_number"

    log_id = fields.Many2one("salary.adjustment.import.log", required=True, ondelete="cascade", index=True)
    row_number = fields.Integer(string="Excel Row")
    status = fields.Selection(
        [("pending", "Pending"), ("imported", "Imported"), ("failed", "Failed"), ("cancelled", "Cancelled")],
        required=True, default="pending", index=True,
    )
    message = fields.Text(string="Problem")
    employee_name = fields.Char(string="Employee (file)")
    employee_id = fields.Many2one("hr.employee", string="Employee")
    input_type_name = fields.Char(string="Type (file)")
    input_type_id = fields.Many2one("hr.payslip.input.type", string="Type")
    monthly_amount = fields.Float(string="Payslip Amount", digits=(16, 3))
    duration_type = fields.Selection(DURATION_SELECTION, string="Duration")
    total_amount = fields.Float(string="Total Amount", digits=(16, 3))
    date_start = fields.Date(string="Start Date")
    note = fields.Char(string="Note")
    adjustment_id = fields.Many2one("hr.salary.attachment", string="Salary Adjustment", ondelete="set null")
    user_id = fields.Many2one(related="log_id.user_id", store=True)
    import_date = fields.Datetime(related="log_id.create_date", string="Import Date")

    def _check_values(self, lookups):
        """Resolve missing employee / type by name and return the list of problems."""
        self.ensure_one()
        employees_by_name, types_by_name = lookups
        errors = []
        if not self.employee_id:
            matches = employees_by_name.get(normalize(self.employee_name))
            if not self.employee_name:
                errors.append(_("Employee is missing."))
            elif not matches:
                errors.append(_("Employee '%s' not found.", self.employee_name))
            elif len(matches) > 1:
                errors.append(_("More than one employee is named '%s'.", self.employee_name))
            else:
                self.employee_id = matches
        if not self.input_type_id:
            input_type = types_by_name.get(normalize(self.input_type_name))
            if input_type:
                self.input_type_id = input_type
            else:
                errors.append(_("Type '%s' not found or not available in adjustments.", self.input_type_name or ""))
        if not self.duration_type:
            errors.append(_("Duration is invalid (use One Time, Limited or Unlimited)."))
        if self.monthly_amount <= 0:
            errors.append(_("Payslip Amount must be greater than 0."))
        if not self.date_start:
            errors.append(_("Start Date is missing."))
        if self.duration_type == "limited" and self.total_amount < self.monthly_amount:
            errors.append(_("Total Amount must be greater than or equal to the Payslip Amount."))
        return errors

    def _prepare_adjustment_vals(self):
        self.ensure_one()
        vals = {
            "employee_ids": [fields.Command.set(self.employee_id.ids)],
            "company_id": self.employee_id.company_id.id or self.log_id.company_id.id,
            "other_input_type_id": self.input_type_id.id,
            "monthly_amount": self.monthly_amount,
            "duration_type": self.duration_type,
            "date_start": self.date_start,
            "description": self.note or False,
        }
        if self.duration_type == "limited":
            vals["total_amount"] = self.total_amount
        return vals

    def _process(self, lookups):
        self.ensure_one()
        errors = self._check_values(lookups)
        if errors:
            self.write({"status": "failed", "message": "\n".join(errors)})
            return
        try:
            with self.env.cr.savepoint():
                adjustment = self.env["hr.salary.attachment"].create(self._prepare_adjustment_vals())
            self.write({"status": "imported", "adjustment_id": adjustment.id, "message": False})
        except Exception as error:  # noqa: BLE001
            _logger.warning("Salary adjustment import %s row %s failed: %s", self.log_id.name, self.row_number, error)
            self.write({"status": "failed", "message": str(error)})
