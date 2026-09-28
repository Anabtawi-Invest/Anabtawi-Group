from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class ConstructionProjectBudgetMaterial(models.Model):
    _name = "construction.project.budget.material"
    _description = "Project Budget Material"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "project_id, id"

    name = fields.Char(string="Material / Item Description", required=True, tracking=True)
    project_id = fields.Many2one(
        "construction.project", string="Project", required=True, ondelete="cascade", tracking=True
    )
    company_id = fields.Many2one(related="project_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="project_id.currency_id", store=True, readonly=True)

    uom = fields.Char(string="Unit of Measure", default="Units", required=True)
    quantity = fields.Float(string="Budgeted Quantity", required=True, default=1.0, tracking=True)
    unit_cost = fields.Monetary(string="Budgeted Unit Cost", required=True, tracking=True)
    total_cost = fields.Monetary(string="Total Cost", compute="_compute_total_cost", store=True)

    po_line_ids = fields.One2many(
        "construction.budget.po.line", "budget_material_id", string="PO Lines"
    )

    qty_purchased = fields.Float(string="Purchased Qty", compute="_compute_quantities", store=True)
    qty_remaining = fields.Float(string="Remaining Qty", compute="_compute_quantities", store=True)
    qty_received = fields.Float(string="Received Qty", compute="_compute_quantities", store=True)
    qty_invoiced = fields.Float(string="Invoiced Qty", compute="_compute_quantities", store=True)

    amount_purchased = fields.Monetary(string="Purchased Amount", compute="_compute_quantities", store=True)
    amount_received = fields.Monetary(string="Received Amount", compute="_compute_quantities", store=True)
    amount_invoiced = fields.Monetary(string="Invoiced Amount", compute="_compute_quantities", store=True)

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("accounting_review", "Pending Accounting"),
            ("ceo_review", "Pending CEO"),
            ("chairman_review", "Pending Chairman"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )

    accounting_user_id = fields.Many2one("res.users", string="Approved by Accounting", readonly=True, copy=False)
    accounting_date = fields.Datetime(string="Accounting Approval Date", readonly=True, copy=False)
    ceo_user_id = fields.Many2one("res.users", string="Approved by CEO", readonly=True, copy=False)
    ceo_date = fields.Datetime(string="CEO Approval Date", readonly=True, copy=False)
    chairman_user_id = fields.Many2one("res.users", string="Approved by Chairman", readonly=True, copy=False)
    chairman_date = fields.Datetime(string="Chairman Approval Date", readonly=True, copy=False)

    reject_reason = fields.Text(string="Rejection Reason", copy=False)
    rejected_by = fields.Many2one("res.users", string="Rejected By", readonly=True, copy=False)

    @api.depends("quantity", "unit_cost")
    def _compute_total_cost(self):
        for rec in self:
            rec.total_cost = rec.quantity * rec.unit_cost

    @api.depends(
        "quantity",
        "po_line_ids",
        "po_line_ids.po_id.state",
        "po_line_ids.quantity",
        "po_line_ids.qty_received",
        "po_line_ids.qty_invoiced",
        "po_line_ids.unit_price",
    )
    def _compute_quantities(self):
        for rec in self:
            valid_po_lines = rec.po_line_ids.filtered(
                lambda l: l.po_id.state in ("approved", "accounting_review", "gm_review", "chairman_review")
            )
            approved_po_lines = rec.po_line_ids.filtered(lambda l: l.po_id.state == "approved")

            purchased_qty = sum(valid_po_lines.mapped("quantity"))
            received_qty = sum(approved_po_lines.mapped("qty_received"))
            invoiced_qty = sum(approved_po_lines.mapped("qty_invoiced"))

            purchased_amt = sum(line.quantity * line.unit_price for line in valid_po_lines)
            received_amt = sum(line.qty_received * line.unit_price for line in approved_po_lines)
            invoiced_amt = sum(line.qty_invoiced * line.unit_price for line in approved_po_lines)

            rec.qty_purchased = purchased_qty
            rec.qty_remaining = max(0.0, rec.quantity - purchased_qty)
            rec.qty_received = received_qty
            rec.qty_invoiced = invoiced_qty

            rec.amount_purchased = purchased_amt
            rec.amount_received = received_amt
            rec.amount_invoiced = invoiced_amt

    @api.constrains("quantity", "unit_cost")
    def _check_values(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError(_("Budgeted quantity must be greater than zero."))
            if rec.unit_cost < 0:
                raise ValidationError(_("Budgeted unit cost cannot be negative."))

    def _check_three_approvers_deletion_auth(self):
        user = self.env.user
        if user.has_group("base.group_system"):
            return
        manager_group = self.env.ref("construction_budget_control.group_construction_manager", raise_if_not_found=False)
        accounting_group = self.env.ref("construction_budget_control.group_construction_accounting_approver", raise_if_not_found=False)
        gm_group = self.env.ref("construction_budget_control.group_construction_gm_approver", raise_if_not_found=False)
        chairman_group = self.env.ref("construction_budget_control.group_construction_chairman_approver", raise_if_not_found=False)

        is_manager = manager_group and user in manager_group.user_ids
        has_all_three = (
            accounting_group and user in accounting_group.user_ids and
            gm_group and user in gm_group.user_ids and
            chairman_group and user in chairman_group.user_ids
        )

        if not (is_manager or has_all_three):
            raise AccessError(_(
                "Deletion Restricted: You cannot delete records without the approval authorization of all three approver roles "
                "(Accounting Manager, CEO, and Chairman)."
            ))

    def unlink(self):
        self._check_three_approvers_deletion_auth()
        return super().unlink()

    def _check_approval_group(self, group_xmlid):

        self.ensure_one()
        group = self.env.ref("construction_budget_control.%s" % group_xmlid, raise_if_not_found=False)
        manager_group = self.env.ref(
            "construction_budget_control.group_construction_manager", raise_if_not_found=False
        )
        allowed = (group and self.env.user in group.user_ids) or (
            manager_group and self.env.user in manager_group.user_ids
        )
        if not allowed:
            raise AccessError(_("You are not authorized to perform this material approval step."))

    def action_submit(self):
        for rec in self:
            if rec.state != "draft":
                continue
            rec.state = "accounting_review"
            rec.message_post(body=_("Material submitted for approval by %s.", rec.env.user.name))

    def action_accounting_approve(self):
        for rec in self:
            rec._check_approval_group("group_construction_accounting_approver")
            if rec.state != "accounting_review":
                raise UserError(_("Material is not pending Accounting approval."))
            rec.write({
                "accounting_user_id": rec.env.user.id,
                "accounting_date": fields.Datetime.now(),
                "state": "ceo_review",
            })
            rec.message_post(body=_("Approved by Accounting (%s). Forwarded to CEO.", rec.env.user.name))

    def action_ceo_approve(self):
        for rec in self:
            rec._check_approval_group("group_construction_gm_approver")
            if rec.state != "ceo_review":
                raise UserError(_("Material is not pending CEO approval."))
            rec.write({
                "ceo_user_id": rec.env.user.id,
                "ceo_date": fields.Datetime.now(),
                "state": "chairman_review",
            })
            rec.message_post(body=_("Approved by CEO (%s). Forwarded to Chairman.", rec.env.user.name))

    def action_chairman_approve(self):
        for rec in self:
            rec._check_approval_group("group_construction_chairman_approver")
            if rec.state != "chairman_review":
                raise UserError(_("Material is not pending Chairman approval."))
            rec.write({
                "chairman_user_id": rec.env.user.id,
                "chairman_date": fields.Datetime.now(),
                "state": "approved",
            })
            rec.message_post(body=_("Approved by Chairman (%s). Material fully approved for purchasing.", rec.env.user.name))

    def action_reject(self):
        stage_group = {
            "accounting_review": "group_construction_accounting_approver",
            "ceo_review": "group_construction_gm_approver",
            "chairman_review": "group_construction_chairman_approver",
        }
        for rec in self:
            if rec.state not in stage_group:
                raise UserError(_("Only materials pending approval can be rejected."))
            rec._check_approval_group(stage_group[rec.state])
            if not rec.reject_reason:
                raise UserError(_("Please provide a rejection reason."))
            rec.write({
                "rejected_by": rec.env.user.id,
                "state": "rejected",
            })
            rec.message_post(body=_("Rejected by %s: %s", rec.env.user.name, rec.reject_reason))

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state != "rejected":
                raise UserError(_("Only rejected materials can be reset to draft."))
            rec.write({
                "state": "draft",
                "accounting_user_id": False, "accounting_date": False,
                "ceo_user_id": False, "ceo_date": False,
                "chairman_user_id": False, "chairman_date": False,
                "reject_reason": False, "rejected_by": False,
            })
