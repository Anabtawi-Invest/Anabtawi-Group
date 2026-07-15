# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


STATES = [
    ("scheduled", "Scheduled"),
    ("in_progress", "In Progress"),
    ("submitted", "Submitted"),
    ("reviewed", "Reviewed"),
    ("approved", "Approved"),
    ("returned", "Returned"),
    ("closed", "Closed"),
]


class QcInspection(models.Model):
    _name = "qc.inspection"
    _description = "Branch Quality Inspection"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "inspection_date desc, id desc"

    name = fields.Char(
        string="Reference", required=True, copy=False, readonly=True,
        default=lambda self: _("New"), index=True,
    )
    branch_id = fields.Many2one(
        "qc.branch", string="Branch", required=True, tracking=True, index=True,
    )
    template_id = fields.Many2one(
        "qc.checklist.template", string="Checklist Template",
        required=True, tracking=True,
    )
    inspector_id = fields.Many2one(
        "res.users", string="Inspector", tracking=True,
        default=lambda self: self.env.user,
    )
    reviewer_id = fields.Many2one(
        "res.users", string="Reviewer", tracking=True,
    )
    inspection_date = fields.Date(
        string="Inspection Date", required=True, tracking=True,
        default=fields.Date.context_today,
    )
    followup_date = fields.Date(string="Follow-up Date", tracking=True)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True,
        default=lambda self: self.env.company,
    )
    state = fields.Selection(
        STATES, string="Status", default="scheduled",
        required=True, tracking=True, index=True,
    )

    factor_ids = fields.One2many(
        "qc.inspection.factor", "inspection_id", string="Factors",
    )
    answer_ids = fields.One2many(
        "qc.inspection.answer", "inspection_id", string="Answers",
    )
    corrective_action_ids = fields.One2many(
        "qc.corrective.action", "inspection_id", string="Corrective Actions",
    )
    corrective_action_count = fields.Integer(
        compute="_compute_corrective_action_count", string="Corrective Actions",
    )

    total_score = fields.Float(
        string="Total Score", compute="_compute_scores", store=True, tracking=True,
    )
    max_score = fields.Float(
        string="Maximum Score", compute="_compute_scores", store=True,
    )
    percentage = fields.Float(
        string="Percentage", compute="_compute_scores", store=True,
    )
    grade_id = fields.Many2one(
        "qc.grade", string="Grade", compute="_compute_scores",
        store=True, tracking=True,
    )
    has_critical = fields.Boolean(
        string="Has Critical Failure", compute="_compute_scores",
        store=True, tracking=True,
    )
    result = fields.Selection(
        [("pending", "Pending"), ("pass", "Passed"), ("fail", "Failed")],
        string="Result", compute="_compute_scores", store=True, tracking=True,
    )
    note = fields.Text(string="General Comments")

    _sql_constraints = [
        ("name_uniq", "unique(name, company_id)",
         "The inspection reference must be unique per company."),
    ]

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends(
        "factor_ids.score", "factor_ids.max_score",
        "factor_ids.has_critical_failure", "branch_id.min_passing_score",
        "state",
    )
    def _compute_scores(self):
        for inspection in self:
            total = sum(inspection.factor_ids.mapped("score"))
            maximum = sum(inspection.factor_ids.mapped("max_score"))
            inspection.total_score = total
            inspection.max_score = maximum
            inspection.percentage = (total / maximum * 100.0) if maximum else 0.0
            has_critical = any(
                inspection.factor_ids.mapped("has_critical_failure"))
            inspection.has_critical = has_critical
            # Grade is based on the score normalised to 100 (only once the
            # checklist actually has scorable content).
            if maximum:
                grade = self.env["qc.grade"]._grade_for_score(
                    inspection.percentage)
                inspection.grade_id = grade.id if grade else False
            else:
                inspection.grade_id = False
            # Result: only meaningful once the inspection is under review.
            if inspection.state in ("scheduled", "in_progress"):
                inspection.result = "pending"
            else:
                min_pass = inspection.branch_id.min_passing_score or 0.0
                if has_critical or inspection.percentage < min_pass:
                    inspection.result = "fail"
                else:
                    inspection.result = "pass"

    @api.depends("corrective_action_ids")
    def _compute_corrective_action_count(self):
        for inspection in self:
            inspection.corrective_action_count = len(
                inspection.corrective_action_ids)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                seq = self.env["ir.sequence"].next_by_code("qc.inspection")
                vals["name"] = seq or _("New")
        inspections = super().create(vals_list)
        for inspection in inspections:
            if inspection.template_id and not inspection.factor_ids:
                inspection._generate_checklist()
        return inspections

    # ------------------------------------------------------------------
    # Checklist generation
    # ------------------------------------------------------------------
    def _generate_checklist(self):
        """(Re)build factor and answer lines from the selected template."""
        Factor = self.env["qc.inspection.factor"]
        Answer = self.env["qc.inspection.answer"]
        for inspection in self:
            inspection.factor_ids.unlink()
            for factor_tmpl in inspection.template_id.factor_ids:
                factor = Factor.create({
                    "inspection_id": inspection.id,
                    "factor_template_id": factor_tmpl.id,
                    "name": factor_tmpl.name,
                    "sequence": factor_tmpl.sequence,
                    "max_score": factor_tmpl.max_score,
                })
                for q_tmpl in factor_tmpl.question_ids:
                    Answer.create({
                        "inspection_id": inspection.id,
                        "factor_id": factor.id,
                        "question_template_id": q_tmpl.id,
                        "name": q_tmpl.name,
                        "sequence": q_tmpl.sequence,
                        "answer_type": q_tmpl.answer_type,
                        "weight": q_tmpl.weight,
                        "is_critical": q_tmpl.is_critical,
                    })
        return True

    def action_load_checklist(self):
        for inspection in self:
            if inspection.state not in ("scheduled", "in_progress"):
                raise UserError(_(
                    "The checklist can only be (re)loaded while the inspection "
                    "is Scheduled or In Progress."))
            if not inspection.template_id:
                raise UserError(_("Select a checklist template first."))
            inspection._generate_checklist()
        return True

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def _ensure_group(self, group_xmlid, message):
        if not self.env.user.has_group(group_xmlid):
            raise UserError(message)

    def action_start(self):
        for inspection in self:
            if inspection.state != "scheduled":
                raise UserError(_("Only scheduled inspections can be started."))
            if not inspection.factor_ids and inspection.template_id:
                inspection._generate_checklist()
        self.write({"state": "in_progress"})
        return True

    def action_submit(self):
        for inspection in self:
            if inspection.state not in ("in_progress", "returned"):
                raise UserError(_(
                    "Only in-progress or returned inspections can be submitted."))
            inspection._check_answers_complete()
        self.write({"state": "submitted"})
        # Critical failures create mandatory corrective actions + alerts.
        for inspection in self:
            inspection._handle_critical_failures()
        return True

    def action_review(self):
        self._ensure_group(
            "anabtawi_branch_qc.group_qc_quality_manager",
            _("Only a Quality Manager can review inspections."))
        for inspection in self:
            if inspection.state != "submitted":
                raise UserError(_("Only submitted inspections can be reviewed."))
            if not inspection.reviewer_id:
                inspection.reviewer_id = self.env.user
        self.write({"state": "reviewed"})
        return True

    def action_return(self):
        self._ensure_group(
            "anabtawi_branch_qc.group_qc_quality_manager",
            _("Only a Quality Manager can return inspections."))
        for inspection in self:
            if inspection.state not in ("submitted", "reviewed"):
                raise UserError(_(
                    "Only submitted or reviewed inspections can be returned."))
        self.write({"state": "returned"})
        return True

    def action_approve(self):
        self._ensure_group(
            "anabtawi_branch_qc.group_qc_quality_manager",
            _("Only a Quality Manager can approve inspections."))
        for inspection in self:
            if inspection.state != "reviewed":
                raise UserError(_("Only reviewed inspections can be approved."))
            if inspection.has_critical and not inspection.corrective_action_ids:
                raise UserError(_(
                    "This inspection has a critical failure. A corrective "
                    "action is mandatory before approval."))
        self.write({"state": "approved"})
        return True

    def action_close(self):
        for inspection in self:
            if inspection.state != "approved":
                raise UserError(_("Only approved inspections can be closed."))
            open_actions = inspection.corrective_action_ids.filtered(
                lambda a: a.state not in ("done", "cancel"))
            if open_actions:
                raise UserError(_(
                    "Cannot close: %d corrective action(s) are still open.")
                    % len(open_actions))
        self.write({"state": "closed"})
        return True

    def action_reset_to_scheduled(self):
        self._ensure_group(
            "anabtawi_branch_qc.group_qc_quality_manager",
            _("Only a Quality Manager can reset inspections."))
        self.write({"state": "scheduled"})
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _check_answers_complete(self):
        self.ensure_one()
        pending = self.answer_ids.filtered(
            lambda a: not a.not_applicable and not a.is_answered)
        if pending:
            raise UserError(_(
                "%d question(s) still need an answer before submitting.")
                % len(pending))

    def _handle_critical_failures(self):
        """Create mandatory corrective actions and optional Quality Alerts."""
        self.ensure_one()
        Corrective = self.env["qc.corrective.action"]
        for factor in self.factor_ids.filtered("has_critical_failure"):
            existing = self.corrective_action_ids.filtered(
                lambda a: a.factor_id == factor)
            if existing:
                continue
            failed_answers = factor.answer_ids.filtered("critical_failed")
            problem = "\n".join(failed_answers.mapped("name"))
            Corrective.create({
                "inspection_id": self.id,
                "branch_id": self.branch_id.id,
                "factor_id": factor.id,
                "problem": problem or factor.name,
                "priority": "3",
                "responsible_id": self.branch_id.manager_id.id or False,
            })
        self._create_quality_alert()

    def _create_quality_alert(self):
        """Raise a standard Odoo Quality Alert on critical failure.

        Controlled by the 'create_quality_alert' setting (default on). The
        creation is defensive: any incompatibility with the installed Quality
        version is logged in the chatter instead of blocking the workflow.
        """
        self.ensure_one()
        if not self.has_critical:
            return
        param = self.env["ir.config_parameter"].sudo().get_param(
            "anabtawi_branch_qc.create_quality_alert", default="True")
        if param in (False, "False", "0", ""):
            return
        if "quality.alert" not in self.env:
            return
        Alert = self.env["quality.alert"].sudo()
        title = _("Critical QC failure - %(branch)s (%(ref)s)") % {
            "branch": self.branch_id.name, "ref": self.name}
        failed = self.factor_ids.filtered("has_critical_failure").mapped("name")
        description = _(
            "Critical quality failure detected during branch inspection "
            "%(ref)s (%(branch)s) on %(date)s.\nFailed factors: %(factors)s"
        ) % {
            "ref": self.name,
            "branch": self.branch_id.name,
            "date": self.inspection_date,
            "factors": ", ".join(failed) or "-",
        }
        vals = {
            "title": title,
            "company_id": self.company_id.id,
            "description": description,
        }
        # team_id is required on quality.alert; use any existing team.
        team = self.env["quality.alert.team"].sudo().search([], limit=1)
        if team:
            vals["team_id"] = team.id
        try:
            alert = Alert.create(vals)
            self.message_post(body=_(
                "Quality Alert %s created for the critical failure.")
                % (alert.display_name or alert.name or ""))
        except Exception:
            # Never let the integration break the inspection flow.
            self.message_post(body=_(
                "Could not create a Quality Alert automatically; please "
                "create one manually if required."))

    def action_view_corrective_actions(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Corrective Actions"),
            "res_model": "qc.corrective.action",
            "view_mode": "list,form",
            "domain": [("inspection_id", "=", self.id)],
            "context": {
                "default_inspection_id": self.id,
                "default_branch_id": self.branch_id.id,
            },
        }

    # ------------------------------------------------------------------
    # Scheduled automation (crons)
    # ------------------------------------------------------------------
    _FREQ_DAYS = {
        "weekly": 7,
        "monthly": 30,
        "quarterly": 91,
        "semiannual": 182,
        "annual": 365,
    }

    @api.model
    def _cron_generate_scheduled_inspections(self):
        """Create the next scheduled inspection for branches that are due."""
        from datetime import timedelta
        today = fields.Date.context_today(self)
        branches = self.env["qc.branch"].search([("active", "=", True)])
        created = self.env["qc.inspection"]
        for branch in branches:
            interval = self._FREQ_DAYS.get(branch.inspection_frequency, 30)
            # Skip if an open inspection already exists.
            open_insp = self.search([
                ("branch_id", "=", branch.id),
                ("state", "in", ("scheduled", "in_progress", "submitted",
                                 "reviewed", "returned")),
            ], limit=1)
            if open_insp:
                continue
            last = self.search([
                ("branch_id", "=", branch.id),
            ], order="inspection_date desc, id desc", limit=1)
            if last and last.inspection_date and \
                    (today - last.inspection_date).days < interval:
                continue
            template = self.env["qc.checklist.template"].search([
                "|", ("company_id", "=", branch.company_id.id),
                ("company_id", "=", False),
            ], limit=1)
            if not template:
                continue
            created |= self.create({
                "branch_id": branch.id,
                "template_id": template.id,
                "inspector_id": branch.inspector_id.id or self.env.uid,
                "inspection_date": today,
                "company_id": branch.company_id.id,
            })
        # Assign an activity to each inspector.
        for insp in created:
            if insp.inspector_id:
                insp.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=insp.inspector_id.id,
                    summary=_("Perform branch quality inspection"),
                )
        return True

    @api.model
    def _cron_send_due_reminders(self):
        """Remind inspectors about inspections not yet submitted."""
        pending = self.search([
            ("state", "in", ("scheduled", "in_progress", "returned")),
        ])
        for insp in pending:
            if not insp.inspector_id:
                continue
            has_todo = insp.activity_ids.filtered(
                lambda a: a.user_id == insp.inspector_id)
            if not has_todo:
                insp.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=insp.inspector_id.id,
                    summary=_("Branch inspection pending submission"),
                )
        return True
