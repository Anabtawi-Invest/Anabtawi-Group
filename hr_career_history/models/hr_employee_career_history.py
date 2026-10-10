import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)

# Wage values are HR-manager data in core; the career managers group is
# granted the same visibility on this model only.
WAGE_GROUPS = "hr.group_hr_manager,hr_career_history.group_career_history_manager"

# Fields that can no longer change once a row has been applied to a version.
LOCKED_AFTER_APPLY = {
    "employee_id",
    "entry_mode",
    "event_type",
    "effective_date",
    "old_job_id",
    "new_job_id",
    "old_department_id",
    "new_department_id",
    "old_wage",
    "new_wage",
}

CRON_BATCH_SIZE = 200
BACKFILL_BATCH_SIZE = 100
PARAM_BACKFILL_LAST_ID = "hr_career_history.backfill_last_employee_id"
BACKFILL_CRON_XMLID = "hr_career_history.ir_cron_backfill_career_history"


class HrEmployeeCareerHistory(models.Model):
    _name = "hr.employee.career.history"
    _description = "Employee Career and Salary History"
    _inherit = ["mail.thread"]
    _order = "effective_date desc, id desc"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        required=True,
        index=True,
        ondelete="cascade",
        check_company=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="employee_id.company_id",
        store=True,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency", related="company_id.currency_id", string="Currency"
    )
    entry_mode = fields.Selection(
        [
            ("apply", "Apply to employee"),
            ("record_only", "Record only (past history)"),
        ],
        string="Entry Mode",
        required=True,
        default="apply",
        tracking=True,
        help="Apply: creates a new employee version on the effective date.\n"
        "Record only: logs a past event, never touches payroll or the current position.",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("scheduled", "Scheduled"),
            ("applied", "Applied"),
            ("recorded", "Recorded"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        index=True,
        copy=False,
        tracking=True,
    )
    event_type = fields.Selection(
        [
            ("hire", "Hire"),
            ("promotion", "Promotion"),
            ("transfer", "Transfer"),
            ("wage_adjustment", "Wage Adjustment"),
            ("other", "Other"),
        ],
        string="Event",
        required=True,
        default="promotion",
    )
    effective_date = fields.Date(
        string="Effective Date",
        required=True,
        index=True,
        default=fields.Date.context_today,
    )

    old_job_id = fields.Many2one("hr.job", string="Previous Job", check_company=True)
    new_job_id = fields.Many2one("hr.job", string="New Job", check_company=True)
    old_department_id = fields.Many2one(
        "hr.department", string="Previous Department", check_company=True
    )
    new_department_id = fields.Many2one(
        "hr.department", string="New Department", check_company=True
    )
    old_wage = fields.Monetary(
        string="Previous Wage", currency_field="currency_id", groups=WAGE_GROUPS
    )
    new_wage = fields.Monetary(
        string="New Wage", currency_field="currency_id", groups=WAGE_GROUPS
    )
    wage_change_pct = fields.Float(
        string="Change %",
        compute="_compute_wage_change_pct",
        digits=(16, 1),
        groups=WAGE_GROUPS,
    )

    reason = fields.Text(string="Reason / Comments")
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "hr_career_history_attachment_rel",
        "history_id",
        "attachment_id",
        string="Attachments",
    )
    version_id = fields.Many2one(
        "hr.version",
        string="Created Version",
        readonly=True,
        copy=False,
        ondelete="set null",
    )

    # ------------------------------------------------------------------
    # Compute / onchange / constraints
    # ------------------------------------------------------------------
    @api.depends("old_wage", "new_wage")
    def _compute_wage_change_pct(self):
        for rec in self:
            if rec.old_wage and rec.new_wage:
                rec.wage_change_pct = (rec.new_wage - rec.old_wage) / rec.old_wage * 100.0
            else:
                rec.wage_change_pct = 0.0

    @api.onchange("employee_id", "effective_date", "entry_mode")
    def _onchange_fill_previous_values(self):
        for rec in self:
            if rec.entry_mode == "apply" and rec.employee_id:
                rec._fill_previous_values()

    def _fill_previous_values(self):
        """Fill 'previous' values from the version valid on the effective date."""
        self.ensure_one()
        employee = self.employee_id.sudo()
        version = employee._get_version(self.effective_date or fields.Date.today())
        if not version:
            return
        self.old_job_id = version.job_id
        self.old_department_id = version.department_id
        self.old_wage = version.wage

    @api.constrains("entry_mode", "effective_date", "new_job_id", "new_department_id",
                    "new_wage", "reason")
    def _check_entry(self):
        today = fields.Date.context_today(self)
        for rec in self:
            has_new_value = rec.new_job_id or rec.new_department_id or rec.new_wage
            if rec.entry_mode == "apply" and not has_new_value:
                raise ValidationError(
                    self.env._("Set at least a new job, department or wage to apply a change.")
                )
            if rec.entry_mode == "record_only":
                if rec.effective_date > today:
                    raise ValidationError(
                        self.env._("A record-only entry cannot be dated in the future. "
                                   "Use 'Apply to employee' for future changes.")
                    )
                if not has_new_value and not rec.reason:
                    raise ValidationError(
                        self.env._("Enter the new values or a reason for the recorded event.")
                    )

    # ------------------------------------------------------------------
    # ORM overrides
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("entry_mode") == "record_only" and not vals.get("state"):
                vals["state"] = "recorded"
        records = super().create(vals_list)
        # Auto-fill "previous" values for live changes the user did not type.
        for rec in records.filtered(
            lambda r: r.entry_mode == "apply"
            and not (r.old_job_id or r.old_department_id or r.old_wage)
        ):
            rec._fill_previous_values()
        return records

    def write(self, vals):
        if LOCKED_AFTER_APPLY & set(vals) and not self.env.context.get("career_history_internal"):
            if any(rec.state == "applied" for rec in self):
                raise UserError(
                    self.env._("An applied entry is locked. Create a new entry to correct it.")
                )
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_applied(self):
        if any(rec.state in ("applied", "scheduled") for rec in self):
            raise UserError(
                self.env._("Applied or scheduled entries cannot be deleted. Cancel them instead.")
            )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _check_manager_access(self):
        if not self.env.su and not self.env.user.has_group(
            "hr_career_history.group_career_history_manager"
        ):
            raise AccessError(
                self.env._("Only Career History Managers can apply or cancel entries.")
            )

    def action_confirm(self):
        """Apply now when the effective date is reached, otherwise schedule."""
        self._check_manager_access()
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.state != "draft" or rec.entry_mode != "apply":
                raise UserError(self.env._("Only draft 'Apply' entries can be confirmed."))
        to_apply = self.filtered(lambda r: r.effective_date <= today)
        (self - to_apply).with_context(career_history_internal=True).write(
            {"state": "scheduled"}
        )
        to_apply._apply()
        return True

    def action_cancel(self):
        self._check_manager_access()
        for rec in self:
            if rec.state == "applied":
                raise UserError(
                    self.env._("An applied entry cannot be cancelled. Create a new entry instead.")
                )
        self.with_context(career_history_internal=True).write({"state": "cancelled"})
        return True

    def action_reset_to_draft(self):
        self._check_manager_access()
        for rec in self:
            if rec.state not in ("scheduled", "cancelled"):
                raise UserError(self.env._("Only scheduled or cancelled entries can be reset."))
        self.with_context(career_history_internal=True).write({"state": "draft"})
        return True

    def _apply(self):
        """Create (or update) the hr.version of the effective date.

        Past versions are never modified, so earlier payslips stay correct.
        """
        for rec in self:
            employee = rec.employee_id.sudo()
            vals = {}
            if rec.new_job_id:
                vals["job_id"] = rec.new_job_id.id
            if rec.new_department_id:
                vals["department_id"] = rec.new_department_id.id
            if rec.new_wage:
                vals["wage"] = rec.new_wage

            same_day = employee.version_ids.filtered(
                lambda v: v.date_version == rec.effective_date
            )[:1]
            if same_day:
                same_day.sudo().write(vals)
                version = same_day
            else:
                version = employee.create_version(
                    {"date_version": rec.effective_date, **vals}
                )
            rec.with_context(career_history_internal=True).write(
                {"state": "applied", "version_id": version.id}
            )

    # ------------------------------------------------------------------
    # Cron
    # ------------------------------------------------------------------
    @api.model
    def _cron_apply_scheduled(self):
        """Apply scheduled entries whose date is reached, in bounded batches."""
        today = fields.Date.context_today(self)
        records = self.search(
            [("state", "=", "scheduled"), ("effective_date", "<=", today)],
            order="effective_date, id",
            limit=CRON_BATCH_SIZE + 1,
        )
        batch = records[:CRON_BATCH_SIZE]
        for rec in batch:
            try:
                with self.env.cr.savepoint():
                    rec._apply()
            except Exception:  # noqa: BLE001 - keep the batch going
                _logger.exception("Career history %s could not be applied", rec.id)
        if len(records) > CRON_BATCH_SIZE:
            cron = self.env.ref(
                "hr_career_history.ir_cron_apply_scheduled_career_history",
                raise_if_not_found=False,
            )
            if cron:
                cron._trigger()

    # ------------------------------------------------------------------
    # One-time backfill from existing employee versions
    # ------------------------------------------------------------------
    @api.model
    def _cron_backfill_from_versions(self):
        """Build the ledger from existing hr.version rows, one batch per run.

        Started once by the post-init hook. Each run handles a bounded number
        of employees, stores a cursor, re-triggers itself and finally
        deactivates its own cron when every employee has been processed.
        """
        params = self.env["ir.config_parameter"].sudo()
        last_id = int(params.get_param(PARAM_BACKFILL_LAST_ID, 0) or 0)
        cron = self.env.ref(BACKFILL_CRON_XMLID, raise_if_not_found=False)
        employees = (
            self.env["hr.employee"]
            .sudo()
            .with_context(active_test=False)
            .search([("id", ">", last_id)], order="id", limit=BACKFILL_BATCH_SIZE)
        )
        if not employees:
            if cron:
                cron.sudo().active = False
            _logger.info("Career history backfill finished.")
            return

        history = self.sudo().with_context(
            tracking_disable=True, mail_create_nolog=True, mail_notrack=True
        )
        for employee in employees:
            try:
                with self.env.cr.savepoint():
                    history._backfill_employee(employee)
            except Exception:  # noqa: BLE001 - one bad employee must not stop the run
                _logger.exception("Career history backfill failed for employee %s", employee.id)
        params.set_param(PARAM_BACKFILL_LAST_ID, employees[-1].id)
        if cron:
            cron._trigger()

    @api.model
    def _backfill_employee(self, employee):
        """Create record-only rows where job, department or wage changed between versions.

        Skips employees that already have ledger rows, so it is safe to re-run.
        Future-dated versions are left to Odoo itself.
        """
        if self.search_count([("employee_id", "=", employee.id)]):
            return
        today = fields.Date.context_today(self)
        versions = (
            self.env["hr.version"]
            .sudo()
            .with_context(active_test=False)
            .search([("employee_id", "=", employee.id)], order="date_version, id")
        )
        reason = "Imported from existing employee version history"
        vals_list = []
        previous = None
        for version in versions:
            if version.date_version > today:
                break
            job, department, wage = version.job_id, version.department_id, version.wage
            if previous is None:
                start = version.contract_date_start
                vals_list.append({
                    "employee_id": employee.id,
                    "entry_mode": "record_only",
                    "state": "recorded",
                    "event_type": "hire",
                    "effective_date": start if start and start <= today else version.date_version,
                    "new_job_id": job.id,
                    "new_department_id": department.id,
                    "new_wage": wage,
                    "reason": reason,
                    "version_id": version.id,
                })
            else:
                job_changed = job != previous.job_id
                dept_changed = department != previous.department_id
                wage_changed = wage != previous.wage
                if job_changed or dept_changed or wage_changed:
                    if job_changed:
                        event_type = "promotion"
                    elif dept_changed:
                        event_type = "transfer"
                    else:
                        event_type = "wage_adjustment"
                    vals_list.append({
                        "employee_id": employee.id,
                        "entry_mode": "record_only",
                        "state": "recorded",
                        "event_type": event_type,
                        "effective_date": version.date_version,
                        "old_job_id": previous.job_id.id,
                        "new_job_id": job.id,
                        "old_department_id": previous.department_id.id,
                        "new_department_id": department.id,
                        "old_wage": previous.wage,
                        "new_wage": wage,
                        "reason": reason,
                        "version_id": version.id,
                    })
            previous = version
        if vals_list:
            self.create(vals_list)
