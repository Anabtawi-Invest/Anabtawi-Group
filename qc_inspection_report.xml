# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class QcReceivingInspection(models.Model):
    """Incoming-goods inspection at a site (supplier delivery control).

    Template-driven checks (truck temperature, packaging, documents, expiry,
    pest evidence) ending in an Accept / Reject decision. Critical failures
    raise corrective actions. Optionally linked to the incoming stock
    transfer and lot for traceability."""
    _name = "qc.receiving.inspection"
    _description = "Receiving Inspection"
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
        domain="[('checklist_type', '=', 'receiving')]", tracking=True,
    )
    date = fields.Date(
        string="Date", required=True, tracking=True,
        default=fields.Date.context_today, index=True,
    )
    user_id = fields.Many2one(
        "res.users", string="Inspected By", tracking=True,
        default=lambda self: self.env.user,
    )
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True,
        default=lambda self: self.env.company,
    )
    supplier_id = fields.Many2one(
        "res.partner", string="Supplier", tracking=True,
        domain="[('is_company', '=', True)]",
    )
    picking_id = fields.Many2one(
        "stock.picking", string="Incoming Transfer",
        domain="[('picking_type_id.code', '=', 'incoming')]",
        help="Optional link to the Odoo receipt for traceability.",
    )
    lot_id = fields.Many2one(
        "stock.lot", string="Lot / Serial",
        help="Optional link to the received lot for recall traceability.",
    )
    lot_ref = fields.Char(
        string="Lot Reference",
        help="Free-text lot/batch reference when no Odoo lot is used.",
    )
    product_description = fields.Char(string="Goods Description")
    state = fields.Selection(
        [
            ("todo", "To Do"),
            ("accepted", "Accepted"),
            ("rejected", "Rejected"),
        ],
        string="Status", default="todo", required=True, tracking=True,
        index=True,
    )
    decision_datetime = fields.Datetime(string="Decided On", readonly=True)
    reject_reason = fields.Text(string="Rejection Reason", tracking=True)
    line_ids = fields.One2many(
        "qc.receiving.line", "receiving_id", string="Checks",
    )
    line_count = fields.Integer(compute="_compute_progress", string="Checks")
    done_count = fields.Integer(compute="_compute_progress", string="Done")
    progress = fields.Float(compute="_compute_progress", string="Progress")
    out_of_range_count = fields.Integer(
        compute="_compute_progress", string="Out of Range",
    )
    unlock_reason = fields.Char(
        string="Unlock Reason", copy=False,
        help="Mandatory justification when a Quality Administrator unlocks a "
             "decided inspection. Posted permanently to the log.",
    )
    unlock_count = fields.Integer(
        string="Times Unlocked", default=0, copy=False, readonly=True,
    )
    note = fields.Text(string="Notes")

    @api.depends("line_ids.is_complete", "line_ids.out_of_range")
    def _compute_progress(self):
        for rec in self:
            lines = rec.line_ids
            done = lines.filtered("is_complete")
            rec.line_count = len(lines)
            rec.done_count = len(done)
            rec.progress = (len(done) / len(lines) * 100.0) if lines else 0.0
            rec.out_of_range_count = len(lines.filtered("out_of_range"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                seq = self.env["ir.sequence"].next_by_code(
                    "qc.receiving.inspection")
                vals["name"] = seq or _("New")
        records = super().create(vals_list)
        for rec in records:
            if rec.template_id and not rec.line_ids:
                rec._generate_lines()
        return records

    def _generate_lines(self):
        Line = self.env["qc.receiving.line"]
        for rec in self:
            rec.line_ids.unlink()
            for factor in rec.template_id.factor_ids:
                for q_tmpl in factor.question_ids:
                    Line.create({
                        "receiving_id": rec.id,
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
                        "ccp_id": q_tmpl.ccp_id.id,
                    })
        return True

    def action_load_lines(self):
        for rec in self:
            if rec.state != "todo":
                raise UserError(_(
                    "Checks can only be reloaded while the inspection is "
                    "To Do."))
            rec._generate_lines()
        return True

    # ------------------------------------------------------------------
    # Decision workflow
    # ------------------------------------------------------------------
    def _check_ready_for_decision(self):
        self.ensure_one()
        pending = self.line_ids.filtered(lambda l: not l.is_complete)
        if pending:
            raise UserError(_(
                "%d check(s) are not completed yet.") % len(pending))
        bad = self.line_ids.filtered(
            lambda l: l.answer_type == "measure" and l.instrument_id
            and not l.instrument_id._is_usable()).mapped("instrument_id")
        if bad:
            raise UserError(_(
                "The following instruments are overdue for calibration and "
                "cannot be used: %s") % ", ".join(bad.mapped("name")))

    def action_accept(self):
        for rec in self:
            if rec.state != "todo":
                raise UserError(_("This inspection is already decided."))
            rec._check_ready_for_decision()
            if rec.supplier_id:
                status = self.env["qc.approved.supplier"]._status_for_partner(
                    rec.supplier_id, rec.company_id)
                if status == "blocked":
                    raise UserError(_(
                        "Supplier %s is BLOCKED on the approved supplier "
                        "list. The delivery cannot be accepted.")
                        % rec.supplier_id.name)
            critical_fail = rec.line_ids.filtered(
                lambda l: l.is_critical
                and (l.out_of_range
                     or (l.answer_type != "measure" and not l.is_done
                         and not l.not_applicable)))
            if critical_fail:
                raise UserError(_(
                    "Critical check(s) failed: %s. The delivery cannot be "
                    "accepted — reject it or resolve the failure.")
                    % ", ".join(critical_fail.mapped("name")))
            rec.write({
                "state": "accepted",
                "user_id": self.env.user.id,
                "decision_datetime": fields.Datetime.now(),
            })
            rec._handle_out_of_range()
        return True

    def action_reject(self):
        for rec in self:
            if rec.state != "todo":
                raise UserError(_("This inspection is already decided."))
            rec._check_ready_for_decision()
            if not rec.reject_reason:
                raise UserError(_(
                    "Enter a rejection reason before rejecting the delivery."))
            rec.write({
                "state": "rejected",
                "user_id": self.env.user.id,
                "decision_datetime": fields.Datetime.now(),
            })
            rec._handle_out_of_range()
            rec._create_rejection_corrective()
        return True

    def action_unlock(self):
        if not self.env.user.has_group(
                "site_quality_control.group_qc_admin"):
            raise UserError(_(
                "Decided inspections are locked. Only a Quality "
                "Administrator can unlock them."))
        for rec in self:
            if rec.state == "todo":
                raise UserError(_("Only decided inspections can be unlocked."))
            if not rec.unlock_reason:
                raise UserError(_(
                    "Enter an unlock reason before unlocking. It will be "
                    "recorded permanently in the log."))
            rec.message_post(body=_(
                "Receiving inspection unlocked by %(user)s. "
                "Reason: %(reason)s") % {
                "user": self.env.user.name,
                "reason": rec.unlock_reason,
            })
            rec.write({
                "state": "todo",
                "decision_datetime": False,
                "unlock_count": rec.unlock_count + 1,
                "unlock_reason": False,
            })
        return True

    # ------------------------------------------------------------------
    # Corrective actions
    # ------------------------------------------------------------------
    def _handle_out_of_range(self):
        self.ensure_one()
        Corrective = self.env["qc.corrective.action"]
        failing = self.line_ids.filtered(
            lambda l: l.is_critical and l.out_of_range)
        for line in failing:
            problem = _(
                "Receiving inspection %(ref)s (%(date)s, supplier "
                "%(supplier)s): '%(task)s' measured %(value).2f %(uom)s "
                "outside the allowed range [%(vmin).2f - %(vmax).2f].") % {
                "ref": self.name,
                "date": self.date,
                "supplier": self.supplier_id.name or "-",
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

    def _create_rejection_corrective(self):
        self.ensure_one()
        self.env["qc.corrective.action"].create({
            "branch_id": self.branch_id.id,
            "problem": _(
                "Delivery rejected — %(ref)s (%(date)s), supplier "
                "%(supplier)s. Reason: %(reason)s") % {
                "ref": self.name,
                "date": self.date,
                "supplier": self.supplier_id.name or "-",
                "reason": self.reject_reason,
            },
            "priority": "2",
            "responsible_id": self.branch_id.manager_id.id or False,
            "company_id": self.company_id.id,
        })


class QcReceivingLine(models.Model):
    _name = "qc.receiving.line"
    _description = "Receiving Inspection Check"
    _order = "receiving_id, section_sequence, sequence, id"

    receiving_id = fields.Many2one(
        "qc.receiving.inspection", string="Inspection",
        required=True, ondelete="cascade", index=True,
    )
    company_id = fields.Many2one(
        related="receiving_id.company_id", store=True, index=True,
    )
    branch_id = fields.Many2one(
        related="receiving_id.branch_id", store=True, index=True,
    )
    question_template_id = fields.Many2one(
        "qc.question.template", string="Question Template",
    )
    section = fields.Char(string="Section")
    section_sequence = fields.Integer(default=10)
    name = fields.Char(string="Check", required=True)
    sequence = fields.Integer(default=10)
    answer_type = fields.Selection(
        [
            ("check", "Done Check"),
            ("measure", "Measure (value)"),
            ("comment", "Comment only"),
            ("pass_fail", "Pass / Fail"),
            ("score_5", "Score 0-5"),
            ("score_10", "Score 0-10"),
        ],
        string="Type", default="check", required=True,
    )
    is_critical = fields.Boolean(string="Critical")
    is_done = fields.Boolean(string="OK")
    value = fields.Float(string="Value")
    target_value = fields.Float(string="Target")
    tolerance_min = fields.Float(string="Min")
    tolerance_max = fields.Float(string="Max")
    uom_name = fields.Char(string="Unit")
    ccp_id = fields.Many2one("qc.ccp", string="CCP")
    instrument_id = fields.Many2one(
        "qc.instrument", string="Instrument",
    )
    comment = fields.Char(string="Comment")
    photo_ids = fields.Many2many(
        "ir.attachment", "qc_receiving_line_photo_rel",
        "line_id", "attachment_id", string="Photos",
        help="Evidence photos for this check (camera capture supported on "
             "mobile).",
    )
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
