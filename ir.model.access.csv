# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class QcSanitationTask(models.Model):
    """Sanitation Standard Operating Procedure (SSOP) master schedule (GMP).

    Defines a recurring cleaning/sanitation task for an area or piece of
    equipment at a site. The cron generates one qc.sanitation.log per due
    date; site staff perform and a supervisor verifies each occurrence."""
    _name = "qc.sanitation.task"
    _description = "Sanitation Task (GMP)"
    _order = "branch_id, name"

    name = fields.Char(string="Task", required=True, translate=True,
                        help="e.g. Deep-clean walk-in fridge, Sanitize prep "
                             "surfaces, Clean grease trap.")
    branch_id = fields.Many2one(
        "qc.branch", string="Site", required=True, index=True,
    )
    area = fields.Char(string="Area / Equipment")
    method = fields.Text(
        string="Method / Chemical",
        help="Cleaning method, chemical/concentration and contact time.",
    )
    frequency = fields.Selection(
        [
            ("daily", "Daily"),
            ("weekly", "Weekly"),
            ("monthly", "Monthly"),
        ],
        string="Frequency", default="daily", required=True,
    )
    requires_verification = fields.Boolean(
        string="Requires Supervisor Verification", default=True,
    )
    company_id = fields.Many2one(
        "res.company", string="Company",
        default=lambda self: self.env.company, index=True,
    )
    active = fields.Boolean(default=True)
    log_ids = fields.One2many(
        "qc.sanitation.log", "task_id", string="Logs",
    )
    note = fields.Text(string="Notes")

    _FREQ_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}

    @api.model
    def _cron_generate_sanitation_logs(self):
        """Create today's sanitation log for every active task that is due
        (no open log exists and the interval since the last log has
        elapsed)."""
        today = fields.Date.context_today(self)
        Log = self.env["qc.sanitation.log"]
        tasks = self.search([("active", "=", True)])
        for task in tasks:
            open_log = Log.search([
                ("task_id", "=", task.id),
                ("state", "=", "todo"),
            ], limit=1)
            if open_log:
                continue
            last = Log.search([
                ("task_id", "=", task.id),
            ], order="date desc, id desc", limit=1)
            interval = task._FREQ_DAYS.get(task.frequency, 1)
            if last and last.date and (today - last.date).days < interval:
                continue
            Log.create({
                "task_id": task.id,
                "branch_id": task.branch_id.id,
                "date": today,
                "company_id": task.company_id.id or task.branch_id.company_id.id,
            })
        return True


class QcSanitationLog(models.Model):
    """Single occurrence of a sanitation task: performed, and optionally
    verified by a supervisor. A failed verification raises a corrective
    action automatically (GMP non-conformance handling)."""
    _name = "qc.sanitation.log"
    _description = "Sanitation Log (GMP)"
    _inherit = ["mail.thread"]
    _order = "date desc, id desc"

    name = fields.Char(
        string="Reference", required=True, copy=False, readonly=True,
        default=lambda self: _("New"), index=True,
    )
    task_id = fields.Many2one(
        "qc.sanitation.task", string="Sanitation Task",
        required=True, index=True,
    )
    branch_id = fields.Many2one(
        "qc.branch", string="Site", required=True, tracking=True, index=True,
    )
    date = fields.Date(
        string="Date", required=True, default=fields.Date.context_today,
        tracking=True, index=True,
    )
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True,
        default=lambda self: self.env.company,
    )
    done_by_id = fields.Many2one(
        "res.users", string="Performed By", tracking=True,
        default=lambda self: self.env.user,
    )
    state = fields.Selection(
        [
            ("todo", "To Do"),
            ("done", "Done"),
            ("verified", "Verified"),
        ],
        string="Status", default="todo", required=True, tracking=True,
        index=True,
    )
    verified_by_id = fields.Many2one(
        "res.users", string="Verified By", tracking=True, readonly=True,
    )
    verification_date = fields.Datetime(string="Verified On", readonly=True)
    verification_result = fields.Selection(
        [("pass", "Passed"), ("fail", "Failed")],
        string="Verification Result", tracking=True,
    )
    photo_before = fields.Binary(string="Before Photo", attachment=True)
    photo_after = fields.Binary(string="After Photo", attachment=True)
    note = fields.Text(string="Notes")
    corrective_action_id = fields.Many2one(
        "qc.corrective.action", string="Corrective Action", readonly=True,
        copy=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                seq = self.env["ir.sequence"].next_by_code("qc.sanitation.log")
                vals["name"] = seq or _("New")
        return super().create(vals_list)

    @api.onchange("task_id")
    def _onchange_task_id(self):
        for log in self:
            if log.task_id:
                log.branch_id = log.task_id.branch_id

    def action_done(self):
        for log in self:
            if log.state != "todo":
                raise UserError(_("This sanitation log is already done."))
            log.write({"state": "done"})
        return True

    def action_verify(self):
        if not self.env.user.has_group(
                "site_quality_control.group_qc_branch_manager"):
            raise UserError(_(
                "Only a Site/Dept Manager or above can verify a sanitation "
                "log."))
        for log in self:
            if log.state != "done":
                raise UserError(_(
                    "Only completed sanitation logs can be verified."))
            if not log.verification_result:
                raise UserError(_(
                    "Set the verification result before verifying."))
            log.write({
                "state": "verified",
                "verified_by_id": self.env.user.id,
                "verification_date": fields.Datetime.now(),
            })
            if log.verification_result == "fail":
                log._create_corrective_action()
        return True

    def _create_corrective_action(self):
        self.ensure_one()
        if self.corrective_action_id:
            return self.corrective_action_id
        action = self.env["qc.corrective.action"].create({
            "branch_id": self.branch_id.id,
            "sanitation_log_id": self.id,
            "problem": _(
                "Sanitation verification failed — %(ref)s (%(date)s): "
                "%(task)s.") % {
                "ref": self.name,
                "date": self.date,
                "task": self.task_id.name,
            },
            "priority": "2",
            "responsible_id": self.branch_id.manager_id.id or False,
            "company_id": self.company_id.id,
        })
        self.corrective_action_id = action.id
        return action
