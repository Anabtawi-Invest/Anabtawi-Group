# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    confirm_approval_ids = fields.One2many(
        "purchase.confirm.approval",
        "order_id",
        string="Confirmation Approvals",
        copy=False,
    )

    current_approval_id = fields.Many2one(
        "purchase.confirm.approval",
        string="Current Approval",
        copy=False,
        readonly=True,
    )

    current_approval_group_id = fields.Many2one(
        "res.groups",
        string="Current Approval Group",
        copy=False,
        readonly=True,
    )

    confirm_approval_status = fields.Selection(
        [
            ("no_rule", "No Approval Required"),
            ("waiting", "Waiting Approval"),
            ("ready", "Ready to Confirm"),
            ("confirmed", "Confirmed"),
            ("cancelled", "Cancelled"),
        ],
        string="Confirmation Approval Status",
        default="no_rule",
        copy=False,
        readonly=True,
    )

    confirm_approval_status_text = fields.Char(
        string="Confirmation Now",
        copy=False,
        readonly=True,
    )

    def _get_confirm_approval_rule(self):
        self.ensure_one()
        return self.env["purchase.confirm.approval.rule"]._get_rule_for_order(self)

    def _get_current_pending_approval(self):
        self.ensure_one()
        return self.confirm_approval_ids.sorted(
            lambda approval: (approval.sequence, approval.id)
        ).filtered(
            lambda approval: approval.required and approval.state == "pending"
        )[:1]

    def _get_approval_display_values(self):
        self.ensure_one()

        current = self._get_current_pending_approval()
        approvals = self.confirm_approval_ids

        if self.state == "cancel":
            return {
                "current_approval_id": False,
                "current_approval_group_id": False,
                "confirm_approval_status": "cancelled",
                "confirm_approval_status_text": _("Cancelled"),
            }

        if self.state in ["purchase", "done"]:
            return {
                "current_approval_id": False,
                "current_approval_group_id": False,
                "confirm_approval_status": "confirmed",
                "confirm_approval_status_text": _("Confirmed"),
            }

        if current:
            return {
                "current_approval_id": current.id,
                "current_approval_group_id": current.group_id.id,
                "confirm_approval_status": "waiting",
                "confirm_approval_status_text": _("Waiting for: %s") % current.group_id.display_name,
            }

        if approvals:
            return {
                "current_approval_id": False,
                "current_approval_group_id": False,
                "confirm_approval_status": "ready",
                "confirm_approval_status_text": _("Ready to Confirm"),
            }

        return {
            "current_approval_id": False,
            "current_approval_group_id": False,
            "confirm_approval_status": "no_rule",
            "confirm_approval_status_text": _("No Approval Required"),
        }

    def _update_approval_display_values(self):
        for order in self:
            vals = order._get_approval_display_values()

            changed_vals = {}
            for field_name, value in vals.items():
                current_value = order[field_name]

                if hasattr(current_value, "id"):
                    current_value = current_value.id or False

                if current_value != value:
                    changed_vals[field_name] = value

            if changed_vals:
                order.with_context(skip_confirm_approval_sync=True).write(changed_vals)

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        orders.with_context(skip_confirm_approval_sync=True)._sync_confirm_approval_steps()
        orders._update_approval_display_values()
        return orders

    def write(self, vals):
        res = super().write(vals)

        if not self.env.context.get("skip_confirm_approval_sync"):
            orders = self.filtered(lambda order: order.state in ["draft", "sent"])
            if orders:
                orders.with_context(skip_confirm_approval_sync=True)._sync_confirm_approval_steps()

            self._update_approval_display_values()

        return res

    def _sync_confirm_approval_steps(self):
        Approval = self.env["purchase.confirm.approval"]
        RuleLine = self.env["purchase.confirm.approval.rule.line"]

        for order in self:
            if order.state not in ["draft", "sent"]:
                continue

            rule = order._get_confirm_approval_rule()

            active_lines = RuleLine
            if rule:
                active_lines = rule.line_ids.filtered(
                    lambda line: line.active
                ).sorted(
                    lambda line: (line.sequence, line.id)
                )

            if not rule or not active_lines:
                order.confirm_approval_ids.unlink()
                continue

            valid_line_ids = active_lines.ids

            obsolete_pending = order.confirm_approval_ids.filtered(
                lambda approval: approval.state == "pending"
                and approval.line_id.id not in valid_line_ids
            )
            obsolete_pending.unlink()

            existing_line_ids = order.confirm_approval_ids.mapped("line_id").ids

            for line in active_lines:
                if line.id not in existing_line_ids:
                    Approval.create(
                        {
                            "order_id": order.id,
                            "rule_id": rule.id,
                            "line_id": line.id,
                            "state": "pending",
                        }
                    )

        self._update_approval_display_values()

    def _user_can_approve_step(self, approval):
        self.ensure_one()

        user = self.env.user
        line = approval.line_id

        if line.group_id not in user.group_ids:
            return False

        if line.specific_user_ids and user not in line.specific_user_ids:
            return False

        if line.exclusive_approval:
            previous_approved = self.confirm_approval_ids.filtered(
                lambda item: item.state == "approved"
                and item.approved_by_id == user
            )

            if previous_approved:
                return False

        return True

    def _notify_current_approval_users(self):
        for order in self:
            approval = order._get_current_pending_approval()

            if not approval:
                continue

            users = approval.line_id.user_to_notify_ids

            if not users:
                users = self.env["res.users"].search(
                    [
                        ("group_ids", "in", [approval.group_id.id]),
                        ("active", "=", True),
                    ]
                )

            partner_ids = users.mapped("partner_id").ids

            if partner_ids:
                order.message_post(
                    body=_(
                        "Purchase confirmation approval is required from group: %s"
                    )
                    % approval.group_id.display_name,
                    partner_ids=partner_ids,
                    subtype_xmlid="mail.mt_comment",
                )

    def _approve_current_step(self):
        for order in self:
            order.with_context(skip_confirm_approval_sync=True)._sync_confirm_approval_steps()

            current = order._get_current_pending_approval()

            if not current:
                order._update_approval_display_values()
                return True

            if not order._user_can_approve_step(current):
                raise AccessError(
                    _("You cannot approve this step. Required group: %s")
                    % current.group_id.display_name
                )

            current.write(
                {
                    "state": "approved",
                    "approved_by_id": self.env.user.id,
                    "approved_date": fields.Datetime.now(),
                }
            )

            order.message_post(
                body=_(
                    "Approval step approved by %(user)s for group %(group)s."
                )
                % {
                    "user": self.env.user.display_name,
                    "group": current.group_id.display_name,
                }
            )

            order._update_approval_display_values()

            if order._get_current_pending_approval():
                order._notify_current_approval_users()

        return True

    def button_confirm(self):
        orders_to_confirm = self.env["purchase.order"]

        for order in self:
            if order.state not in ["draft", "sent"]:
                orders_to_confirm |= order
                continue

            order.with_context(skip_confirm_approval_sync=True)._sync_confirm_approval_steps()
            order._update_approval_display_values()

            current = order._get_current_pending_approval()

            if current:
                order._approve_current_step()

                if order._get_current_pending_approval():
                    order._update_approval_display_values()
                    continue

            orders_to_confirm |= order

        result = True

        if orders_to_confirm:
            result = super(PurchaseOrder, orders_to_confirm).button_confirm()
            orders_to_confirm._update_approval_display_values()

        return result
