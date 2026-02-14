from odoo import models, fields, _
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    approval_state = fields.Selection(
        [
            ("none", "None"),
            ("to_approve", "To Approve"),
            ("approved", "Approved"),
        ],
        default="none",
        tracking=True,
        copy=False,
    )

    approval_stage = fields.Selection(
        [
            ("manager", "Manager"),
            ("accounting", "Accounting"),
        ],
        default="manager",
        tracking=True,
        copy=False,
    )

    approval_line_ids = fields.One2many(
        "po.approval.line",
        "order_id",
        copy=False,
    )

    next_group = fields.Char(copy=False)

    # =====================================================
    # Submit for approval
    # =====================================================
    def action_submit_for_approval(self):
        for order in self:
            order.approval_state = "to_approve"
            order.approval_stage = "manager"

            order.message_post(
                body=_("RFQ submitted for approval by %s") % self.env.user.name
            )

            order._create_stage_lines(stage="manager")

    # =====================================================
    # Create approval lines per stage
    # =====================================================
    def _create_stage_lines(self, stage):
        self.ensure_one()

        if stage == "manager":
            group = self.env.ref("po_multi_approval.group_purchase_manager_custom")
        else:
            group = self.env.ref("po_multi_approval.group_purchase_accounting")

        users = self.env["res.users"].search([("group_ids", "in", [group.id])])

        if not users:
            raise UserError(_("No users found in group: %s") % group.name)

        for user in users:
            self.env["po.approval.line"].create({
                "order_id": self.id,
                "user_id": user.id,
                "group_name": group.name,
                "state": "pending",
            })

        self.next_group = group.name

        self.message_post(
            body=_("Waiting approval from group: %s") % group.name
        )

    # =====================================================
    # Approve step (one approver per group is enough)
    # =====================================================
    def action_approve_step(self):
        for order in self:
            # find current user's pending line
            my_line = order.approval_line_ids.filtered(
                lambda l: l.user_id == self.env.user and l.state == "pending"
            )[:1]

            if not my_line:
                raise UserError(_("Not allowed to approve this PO"))

            # ✅ approve whole group with one click (avoid stuck)
            same_group_pending = order.approval_line_ids.filtered(
                lambda l: l.group_name == my_line.group_name and l.state == "pending"
            )
            same_group_pending.write({"state": "approved"})

            order.message_post(
                body=_("%s approved (%s)") % (self.env.user.name, my_line.group_name)
            )

            # =================================================
            # Move to next stage if needed
            # =================================================
            # If amount > 10000: Manager then Accounting
            if order.amount_total > 10000 and order.approval_stage == "manager":
                order.approval_stage = "accounting"

                # create accounting lines only if not already created
                accounting_group = self.env.ref("po_multi_approval.group_purchase_accounting").name
                has_accounting_pending = order.approval_line_ids.filtered(
                    lambda l: l.group_name == accounting_group and l.state == "pending"
                )
                if not has_accounting_pending:
                    order._create_stage_lines(stage="accounting")
                return

            # Final approval (either <=10000 after manager, or >10000 after accounting)
            order.approval_state = "approved"
            order.message_post(body=_("All approvals completed. Ready for confirmation."))

    # =====================================================
    # Confirm (ACCOUNTING ONLY)
    # =====================================================
    def button_confirm(self):
        accounting_group_xmlid = "po_multi_approval.group_purchase_accounting"

        for order in self:
            if order.approval_state != "approved":
                raise UserError(_("PO requires approval first"))

            if not self.env.user.has_group(accounting_group_xmlid):
                raise UserError(_("Only Accounting can confirm this PO"))

            order.message_post(
                body=_("PO confirmed by Accounting: %s") % self.env.user.name
            )

        return super().button_confirm()
