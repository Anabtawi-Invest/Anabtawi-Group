import base64
import io

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None

APPROVAL_STATES = ("accounting_review", "gm_review", "chairman_review")


class ConstructionBudgetPo(models.Model):
    _name = "construction.budget.po"
    _description = "Construction Purchase Order (Budget Control)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char(
        string="Reference", required=True, copy=False, readonly=True, default=lambda self: _("New")
    )
    project_id = fields.Many2one(
        "construction.project", string="Project", required=True, tracking=True, ondelete="restrict"
    )
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="project_id.currency_id", store=True, readonly=True)
    vendor_id = fields.Many2one(
        "res.partner", string="Vendor / Subcontractor", required=True, tracking=True
    )
    po_number = fields.Char(string="PO Reference No.", help="Reference number printed on the uploaded PO document")
    po_date = fields.Date(string="PO Date", default=fields.Date.context_today)
    description = fields.Text(string="Description / Scope of Work")
    amount = fields.Monetary(string="PO Amount", required=True, tracking=True)

    po_document = fields.Binary(string="PO Document", attachment=True)
    po_document_filename = fields.Char(string="Document Filename")

    requested_by = fields.Many2one(
        "res.users", string="Requested By", default=lambda self: self.env.user, readonly=True
    )

    line_ids = fields.One2many("construction.budget.po.line", "po_id", string="Bill of Materials")
    lines_total = fields.Monetary(compute="_compute_lines_total", string="BOM Lines Total", store=True)
    bom_mismatch = fields.Boolean(compute="_compute_lines_total")

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("accounting_review", "Pending Accounting"),
            ("gm_review", "Pending General Manager"),
            ("chairman_review", "Pending Chairman"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )

    gm_required = fields.Boolean(compute="_compute_approval_requirements", store=True)
    chairman_required = fields.Boolean(compute="_compute_approval_requirements", store=True)

    accounting_user_id = fields.Many2one("res.users", string="Approved by Accounting", readonly=True, copy=False)
    accounting_date = fields.Datetime(string="Accounting Approval Date", readonly=True, copy=False)
    gm_user_id = fields.Many2one("res.users", string="Approved by GM", readonly=True, copy=False)
    gm_date = fields.Datetime(string="GM Approval Date", readonly=True, copy=False)
    chairman_user_id = fields.Many2one("res.users", string="Approved by Chairman", readonly=True, copy=False)
    chairman_date = fields.Datetime(string="Chairman Approval Date", readonly=True, copy=False)

    reject_reason = fields.Text(string="Rejection Reason", copy=False)
    rejected_by = fields.Many2one("res.users", string="Rejected By", readonly=True, copy=False)
    rejected_stage = fields.Char(string="Rejected At Stage", readonly=True, copy=False)

    project_remaining_budget = fields.Monetary(
        related="project_id.remaining_budget", string="Project Remaining Budget", readonly=True
    )

    @api.depends("line_ids.subtotal", "amount")
    def _compute_lines_total(self):
        for rec in self:
            total = sum(rec.line_ids.mapped("subtotal"))
            rec.lines_total = total
            rec.bom_mismatch = bool(rec.line_ids) and abs(total - rec.amount) > 0.01

    @api.depends("amount", "company_id")
    def _compute_approval_requirements(self):
        for rec in self:
            company = rec.company_id or rec.env.company
            gm_threshold = company.construction_gm_threshold or 0.0
            chairman_threshold = company.construction_chairman_threshold or 0.0
            rec.chairman_required = bool(rec.amount) and rec.amount >= chairman_threshold
            rec.gm_required = rec.chairman_required or (bool(rec.amount) and rec.amount >= gm_threshold)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.budget.po") or _("New")
        return super().create(vals_list)

    @api.constrains("amount")
    def _check_amount(self):
        for rec in self:
            if rec.amount is not None and rec.amount < 0:
                raise ValidationError(_("The PO amount cannot be negative."))

    def _check_approval_group(self, group_xmlid):
        self.ensure_one()
        group = self.env.ref("construction_budget_control.%s" % group_xmlid, raise_if_not_found=False)
        manager_group = self.env.ref(
            "construction_budget_control.group_construction_manager", raise_if_not_found=False
        )
        allowed = (group and self.env.user in group.users) or (
            manager_group and self.env.user in manager_group.users
        )
        if not allowed:
            raise AccessError(_("You are not authorized to perform this approval step."))

    def _notify_approvers(self, group_xmlid):
        group = self.env.ref("construction_budget_control.%s" % group_xmlid, raise_if_not_found=False)
        if not group:
            return
        for user in group.users:
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("PO approval required: %s", self.name),
                note=_("Project: %s - Amount: %s", self.project_id.name, self.amount),
                user_id=user.id,
            )

    def action_submit(self):
        for rec in self:
            if rec.state != "draft":
                continue
            if not rec.po_document:
                raise UserError(_("Please upload the Purchase Order document before submitting."))
            if not rec.amount or rec.amount <= 0:
                raise UserError(_("The PO amount must be greater than zero."))
            if not rec.line_ids:
                raise UserError(_("Please add at least one Bill of Materials line before submitting."))
            project = rec.project_id
            remaining = project.total_budget - project.approved_amount - project.pending_amount
            if rec.amount > remaining:
                raise UserError(
                    _(
                        "This Purchase Order of %(amount)s exceeds the remaining budget of project "
                        "'%(project)s' (%(remaining)s remaining). Submission is blocked.",
                        amount=rec.amount, project=project.name, remaining=remaining,
                    )
                )
            rec.state = "accounting_review"
            rec.message_post(body=_("Submitted for approval by %s.", rec.env.user.name))
            rec._notify_approvers("group_construction_accounting_approver")

    def action_accounting_approve(self):
        for rec in self:
            rec._check_approval_group("group_construction_accounting_approver")
            if rec.state != "accounting_review":
                raise UserError(_("This PO is not waiting for Accounting approval."))
            rec.write({"accounting_user_id": rec.env.user.id, "accounting_date": fields.Datetime.now()})
            if rec.gm_required:
                rec.state = "gm_review"
                rec.message_post(body=_(
                    "Approved by Accounting (%s). Forwarded to General Manager.", rec.env.user.name
                ))
                rec._notify_approvers("group_construction_gm_approver")
            else:
                rec.state = "approved"
                rec.message_post(body=_(
                    "Approved by Accounting (%s). Final approval - below GM threshold.", rec.env.user.name
                ))

    def action_gm_approve(self):
        for rec in self:
            rec._check_approval_group("group_construction_gm_approver")
            if rec.state != "gm_review":
                raise UserError(_("This PO is not waiting for General Manager approval."))
            rec.write({"gm_user_id": rec.env.user.id, "gm_date": fields.Datetime.now()})
            if rec.chairman_required:
                rec.state = "chairman_review"
                rec.message_post(body=_(
                    "Approved by General Manager (%s). Forwarded to Chairman.", rec.env.user.name
                ))
                rec._notify_approvers("group_construction_chairman_approver")
            else:
                rec.state = "approved"
                rec.message_post(body=_("Approved by General Manager (%s). Final approval.", rec.env.user.name))

    def action_chairman_approve(self):
        for rec in self:
            rec._check_approval_group("group_construction_chairman_approver")
            if rec.state != "chairman_review":
                raise UserError(_("This PO is not waiting for Chairman approval."))
            rec.write({
                "chairman_user_id": rec.env.user.id,
                "chairman_date": fields.Datetime.now(),
                "state": "approved",
            })
            rec.message_post(body=_("Approved by Chairman (%s). Final approval.", rec.env.user.name))

    def action_reject(self):
        stage_group = {
            "accounting_review": "group_construction_accounting_approver",
            "gm_review": "group_construction_gm_approver",
            "chairman_review": "group_construction_chairman_approver",
        }
        for rec in self:
            if rec.state not in APPROVAL_STATES:
                raise UserError(_("Only Purchase Orders pending approval can be rejected."))
            rec._check_approval_group(stage_group[rec.state])
            if not rec.reject_reason:
                raise UserError(_("Please fill in the Rejection Reason before rejecting."))
            rec.write({
                "rejected_by": rec.env.user.id,
                "rejected_stage": dict(rec._fields["state"].selection).get(rec.state),
                "state": "rejected",
            })
            rec.message_post(body=_(
                "Rejected by %(user)s: %(reason)s", user=rec.env.user.name, reason=rec.reject_reason
            ))

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state != "rejected":
                raise UserError(_("Only rejected Purchase Orders can be reset to draft."))
            rec.write({
                "state": "draft",
                "accounting_user_id": False, "accounting_date": False,
                "gm_user_id": False, "gm_date": False,
                "chairman_user_id": False, "chairman_date": False,
                "reject_reason": False, "rejected_by": False, "rejected_stage": False,
            })

    def action_cancel(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only draft Purchase Orders can be cancelled."))
            rec.state = "cancelled"

    def action_export_bom_excel(self):
        self.ensure_one()
        if not xlsxwriter:
            raise UserError(_(
                "The 'xlsxwriter' Python library is required for Excel export. "
                "Please ask your administrator to install it (pip install xlsxwriter)."
            ))
        attachment = self._build_bom_workbook_single()
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    def _build_bom_workbook_single(self):
        self.ensure_one()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        title_fmt = workbook.add_format({"bold": True, "font_size": 14})
        bold = workbook.add_format({"bold": True})
        header_fmt = workbook.add_format({"bold": True, "bg_color": "#D9D9D9", "border": 1})
        cell_fmt = workbook.add_format({"border": 1})
        money_fmt = workbook.add_format({"border": 1, "num_format": "#,##0.00"})
        total_fmt = workbook.add_format({"bold": True, "border": 1, "num_format": "#,##0.00"})

        sheet = workbook.add_worksheet("BOM")
        sheet.write(0, 0, "Bill of Materials - %s" % self.name, title_fmt)
        sheet.write(1, 0, "Project:", bold)
        sheet.write(1, 1, self.project_id.name or "")
        sheet.write(2, 0, "Vendor:", bold)
        sheet.write(2, 1, self.vendor_id.name or "")
        sheet.write(3, 0, "PO Reference:", bold)
        sheet.write(3, 1, self.po_number or "")
        sheet.write(4, 0, "Status:", bold)
        sheet.write(4, 1, dict(self._fields["state"].selection).get(self.state))

        self._write_bom_lines(sheet, header_fmt, cell_fmt, money_fmt, total_fmt, start_row=6)

        attachment = self.env["ir.attachment"].create({
            "name": "BOM_%s.xlsx" % self.name,
            "datas": self._workbook_to_base64(workbook, output),
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return attachment

    def _write_bom_lines(self, sheet, header_fmt, cell_fmt, money_fmt, total_fmt, start_row):
        headers = ["#", "Description", "UoM", "Quantity", "Unit Price", "Subtotal"]
        row = start_row
        for col, h in enumerate(headers):
            sheet.write(row, col, h, header_fmt)
        row += 1
        for idx, line in enumerate(self.line_ids, start=1):
            sheet.write(row, 0, idx, cell_fmt)
            sheet.write(row, 1, line.description or "", cell_fmt)
            sheet.write(row, 2, line.uom or "", cell_fmt)
            sheet.write(row, 3, line.quantity, cell_fmt)
            sheet.write(row, 4, line.unit_price, money_fmt)
            sheet.write(row, 5, line.subtotal, money_fmt)
            row += 1
        sheet.merge_range(row, 0, row, 4, "Total", total_fmt)
        sheet.write(row, 5, self.lines_total, total_fmt)
        sheet.set_column(1, 1, 40)
        sheet.set_column(2, 5, 15)
        return row

    @staticmethod
    def _workbook_to_base64(workbook, output):
        workbook.close()
        output.seek(0)
        return base64.b64encode(output.read())
