# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class QcDailyChecklist(models.Model):
    """Daily operational checklist filled by the site itself.

    No grading, no review workflow: staff tick each task as done and record
    measured values (e.g. fridge temperatures). Out-of-tolerance measures are
    flagged and, when critical, raise a corrective action on completion.
    """
    _name = "qc.daily.checklist"
    _description = "Daily Site Checklist"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(
        string="Reference", required=True, copy=False, readonly=True,
        default=lambda self: _("New"), index=True,
    )
    branch_id = fields.Many2one(
        "qc.branch", string="Site", required=True, tracking=True, index=True,
    )
    template_id = fields.Many2one(
        "qc.checklist.template", string="Checklist Template", required=True,
        domain="[('checklist_type', '=', 'daily')]", tracking=True,
    )
    date = fields.Date(
        string="Date", required=True, tracking=True,
        default=fields.Date.context_today, index=True,
    )
    user_id = fields.Many2one(
        "res.users", string="Filled By", tracking=True,
        default=lambda self: self.env.user,
    )
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True,
        default=lambda self: self.env.company,
    )
    state = fields.Selection(
        [("todo", "To Do"), ("done", "Done")],
        string="Status", default="todo", required=True, tracking=True,
        index=True,
    )
    done_datetime = fields.Datetime(string="Completed On", readonly=True)
    line_ids = fields.One2many(
        "qc.daily.checklist.line", "checklist_id", string="Lines",
    )
    line_count = fields.Integer(compute="_compute_progress", string="Tasks")
    done_count = fields.Integer(compute="_compute_progress", string="Done Tasks")
    progress = fields.Float(compute="_compute_progress", string="Progress")
    out_of_range_count = fields.Integer(
        compute="_compute_progress", string="Out of Range",
    )
    note = fields.Text(string="Notes")

    _sql_constraints = [
        ("branch_date_template_uniq",
         "unique(branch_id, date, template_id, company_id)",
         "A daily checklist already exists for this site, template and date."),
    ]

    @api.depends("line_ids.is_complete", "line_ids.out_of_range")
    def _compute_progress(self):
        for checklist in self:
            lines = checklist.line_ids
            done = lines.filtered("is_complete")
            checklist.line_count = len(lines)
            checklist.done_count = len(done)
            checklist.progress = (
                len(done) / len(lines) * 100.0) if lines else 0.0
            checklist.out_of_range_count = len(
                lines.filtered("out_of_range"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                seq = self.env["ir.sequence"].next_by_code("qc.daily.checklist")
                vals["name"] = seq or _("New")
        checklists = super().create(vals_list)
        for checklist in checklists:
            if checklist.template_id and not checklist.line_ids:
                checklist._generate_lines()
        return checklists

    def _generate_lines(self):
        """Build checklist lines from the daily template."""
        Line = self.env["qc.daily.checklist.line"]
        for checklist in self:
            checklist.line_ids.unlink()
            for factor in checklist.template_id.factor_ids:
                for q_tmpl in factor.question_ids:
                    Line.create({
                        "checklist_id": checklist.id,
                        "section": factor.name,
                        "section_sequence": factor.sequence,
                        "question_template_id": q_tmpl.id,
                        "name": q_tmpl.name,
                        "sequence": q_tmpl.sequence,
                        "answer_type": q_tmpl.answer_type,
                        "is_critical": q_tmpl.is_critical,
                        "target_value": q_tmpl.target_value,
                        "tolerance_min": q_tmpl.tolerance_min,
                        "tolerance_max": q_tmpl.tolerance_max,
                        "uom_name": q_tmpl.uom_name,
                    })
        return True

    def action_load_lines(self):
        for checklist in self:
            if checklist.state != "todo":
                raise UserError(_(
                    "Lines can only be reloaded while the checklist is To Do."))
            checklist._generate_lines()
        return True

    def action_done(self):
        for checklist in self:
            if checklist.state != "todo":
                raise UserError(_("This checklist is already completed."))
            pending = checklist.line_ids.filtered(
                lambda l: not l.is_complete)
            if pending:
                raise UserError(_(
                    "%d task(s) are not completed yet.") % len(pending))
            checklist.write({
                "state": "done",
                "user_id": self.env.user.id,
                "done_datetime": fields.Datetime.now(),
            })
            checklist._handle_out_of_range()
        return True

    def action_reset(self):
        self.write({"state": "todo", "done_datetime": False})
        return True

    def _handle_out_of_range(self):
        """Create corrective actions for critical out-of-range measures and
        critical unchecked tasks."""
        self.ensure_one()
        Corrective = self.env["qc.corrective.action"]
        failing = self.line_ids.filtered(
            lambda l: l.is_critical and l.out_of_range)
        for line in failing:
            problem = _(
                "Daily checklist %(ref)s (%(date)s): '%(task)s' measured "
                "%(value).2f %(uom)s outside the allowed range "
                "[%(vmin).2f - %(vmax).2f].") % {
                "ref": self.name,
                "date": self.date,
                "task": line.name,
                "value": line.value,
                "uom": line.uom_name or "",
                "vmin": line.tolerance_min,
                "vmax": line.tolerance_max,
            }
            Corrective.create({
                "branch_id": self.branch_id.id,
                "problem": problem,
                "priority": "3",
                "responsible_id": self.branch_id.manager_id.id or False,
                "company_id": self.company_id.id,
            })
        if failing:
            self.message_post(body=_(
                "%d corrective action(s) created for critical out-of-range "
                "measures.") % len(failing))

    # ------------------------------------------------------------------
    # Scheduled automation (cron)
    # ------------------------------------------------------------------
    @api.model
    def _cron_generate_daily_checklists(self):
        """Create today's checklist for every active site, for every active
        daily template of its company."""
        today = fields.Date.context_today(self)
        branches = self.env["qc.branch"].search([("active", "=", True)])
        templates = self.env["qc.checklist.template"].search([
            ("checklist_type", "=", "daily"),
        ])
        for branch in branches:
            branch_templates = templates.filtered(
                lambda t: not t.company_id
                or t.company_id == branch.company_id)
            for template in branch_templates:
                existing = self.search([
                    ("branch_id", "=", branch.id),
                    ("template_id", "=", template.id),
                    ("date", "=", today),
                ], limit=1)
                if existing:
                    continue
                checklist = self.create({
                    "branch_id": branch.id,
                    "template_id": template.id,
                    "date": today,
                    "company_id": branch.company_id.id,
                })
                if branch.manager_id:
                    checklist.activity_schedule(
                        "mail.mail_activity_data_todo",
                        user_id=branch.manager_id.id,
                        summary=_("Fill today's site checklist"),
                    )
        return True


class QcDailyChecklistLine(models.Model):
    _name = "qc.daily.checklist.line"
    _description = "Daily Site Checklist Line"
    _order = "checklist_id, section_sequence, sequence, id"

    checklist_id = fields.Many2one(
        "qc.daily.checklist", string="Checklist",
        required=True, ondelete="cascade", index=True,
    )
    company_id = fields.Many2one(
        related="checklist_id.company_id", store=True, index=True,
    )
    branch_id = fields.Many2one(
        related="checklist_id.branch_id", store=True, index=True,
    )
    question_template_id = fields.Many2one(
        "qc.question.template", string="Question Template",
    )
    section = fields.Char(string="Section")
    section_sequence = fields.Integer(default=10)
    name = fields.Char(string="Task", required=True)
    sequence = fields.Integer(default=10)
    answer_type = fields.Selection(
        [
            ("check", "Done Check"),
            ("measure", "Measure (value)"),
            ("comment", "Comment only"),
            # Graded types may appear if a daily template reuses questions;
            # they behave like a simple done check here.
            ("pass_fail", "Pass / Fail"),
            ("score_5", "Score 0-5"),
            ("score_10", "Score 0-10"),
        ],
        string="Type", default="check", required=True,
    )
    is_critical = fields.Boolean(string="Critical")

    # Captured values
    is_done = fields.Boolean(string="Done")
    value = fields.Float(string="Value")
    target_value = fields.Float(string="Target")
    tolerance_min = fields.Float(string="Min")
    tolerance_max = fields.Float(string="Max")
    uom_name = fields.Char(string="Unit")
    comment = fields.Char(string="Comment")
    photo = fields.Binary(string="Photo", attachment=True)
    not_applicable = fields.Boolean(string="N/A")

    out_of_range = fields.Boolean(
        string="Out of Range", compute="_compute_status", store=True,
    )
    is_complete = fields.Boolean(
        string="Completed", compute="_compute_status", store=True,
    )

    @api.depends(
        "answer_type", "is_done", "value", "not_applicable",
        "tolerance_min", "tolerance_max", "comment",
    )
    def _compute_status(self):
        for line in self:
            if line.not_applicable:
                line.is_complete = True
                line.out_of_range = False
                continue
            if line.answer_type == "comment":
                line.is_complete = bool(line.comment)
                line.out_of_range = False
                continue
            # Both checks and measures are confirmed with the Done tick;
            # measures additionally validate the entered value.
            line.is_complete = line.is_done
            if line.answer_type == "measure" and line.is_done \
                    and line.tolerance_min < line.tolerance_max:
                line.out_of_range = not (
                    line.tolerance_min <= line.value <= line.tolerance_max)
            else:
                line.out_of_range = False

    @api.onchange("value")
    def _onchange_value(self):
        for line in self:
            if line.answer_type == "measure" and line.value:
                line.is_done = True

    @api.onchange("not_applicable")
    def _onchange_not_applicable(self):
        for line in self:
            if line.not_applicable:
                line.is_done = False
                line.value = 0.0
