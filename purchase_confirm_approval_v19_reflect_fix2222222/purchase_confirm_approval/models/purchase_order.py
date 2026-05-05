# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, AccessError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    confirm_approval_ids = fields.One2many(
        'purchase.confirm.approval',
        'order_id',
        string='Confirmation Approvals',
        copy=False,
    )
    current_approval_id = fields.Many2one(
        'purchase.confirm.approval',
        string='Current Approval',
        compute='_compute_confirm_approval_state',
        store=True,
    )
    current_approval_group_id = fields.Many2one(
        'res.groups',
        string='Current Approval Group',
        compute='_compute_confirm_approval_state',
        store=True,
    )
    confirm_approval_status = fields.Selection(
        [
            ('no_rule', 'No Approval Required'),
            ('waiting', 'Waiting Approval'),
            ('ready', 'Ready to Confirm'),
            ('confirmed', 'Confirmed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Confirmation Approval Status',
        compute='_compute_confirm_approval_state',
        store=True,
    )
    confirm_approval_status_text = fields.Char(
        string='Confirmation Now',
        compute='_compute_confirm_approval_state',
        store=True,
    )

    @api.depends(
        'state',
        'confirm_approval_ids.state',
        'confirm_approval_ids.sequence',
        'confirm_approval_ids.group_id',
        'confirm_approval_ids.required',
    )
    def _compute_confirm_approval_state(self):
        for order in self:
            current = order.confirm_approval_ids.filtered(
                lambda approval: approval.required and approval.state == 'pending'
            )[:1]

            order.current_approval_id = current.id if current else False
            order.current_approval_group_id = current.group_id.id if current else False

            if order.state == 'cancel':
                order.confirm_approval_status = 'cancelled'
                order.confirm_approval_status_text = _('Cancelled')
            elif order.state in ('purchase', 'done'):
                order.confirm_approval_status = 'confirmed'
                order.confirm_approval_status_text = _('Confirmed')
            elif current:
                order.confirm_approval_status = 'waiting'
                order.confirm_approval_status_text = _('Waiting for: %s') % current.group_id.display_name
            elif order.confirm_approval_ids:
                order.confirm_approval_status = 'ready'
                order.confirm_approval_status_text = _('Ready to Confirm')
            else:
                order.confirm_approval_status = 'no_rule'
                order.confirm_approval_status_text = _('No Approval Required')

    def _get_confirm_approval_rule(self):
        self.ensure_one()
        return self.env['purchase.confirm.approval.rule']._get_rule_for_order(self)


    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        orders._sync_confirm_approval_steps()
        orders._compute_confirm_approval_state()
        return orders

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('skip_confirm_approval_sync'):
            draft_orders = self.filtered(lambda order: order.state in ('draft', 'sent'))
            if draft_orders:
                draft_orders.with_context(skip_confirm_approval_sync=True)._sync_confirm_approval_steps()
                draft_orders._compute_confirm_approval_state()
        return res

    def _sync_confirm_approval_steps(self):
        """Create missing approval step records dynamically from the active configuration."""
        Approval = self.env['purchase.confirm.approval']

        for order in self:
            if order.state not in ('draft', 'sent'):
                continue

            rule = order._get_confirm_approval_rule()
            active_required_lines = rule.line_ids.filtered(lambda line: line.active).sorted(lambda line: (line.sequence, line.id)) if rule else False

            if not rule or not active_required_lines:
                # No configuration means no approval is required.
                order.confirm_approval_ids.unlink()
                continue

            existing_by_line = {approval.line_id.id: approval for approval in order.confirm_approval_ids}

            # Remove approvals that no longer exist in the active rule, but keep already-approved history
            # only when it belongs to the current rule line set.
            valid_line_ids = active_required_lines.ids
            obsolete_pending = order.confirm_approval_ids.filtered(
                lambda approval: approval.state == 'pending' and approval.line_id.id not in valid_line_ids
            )
            obsolete_pending.unlink()

            for line in active_required_lines:
                if line.id not in existing_by_line:
                    Approval.create({
                        'order_id': order.id,
                        'rule_id': rule.id,
                        'line_id': line.id,
                        'state': 'pending',
                    })

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
                lambda item: item.state == 'approved' and item.approved_by_id == user
            )
            if previous_approved:
                return False

        return True

    def _notify_current_approval_users(self):
        for order in self:
            approval = order.current_approval_id
            if not approval:
                continue
            users = approval.line_id.user_to_notify_ids
            if not users:
                users = self.env['res.users'].search([('group_ids', 'in', [approval.group_id.id]), ('active', '=', True)])
            partner_ids = users.mapped('partner_id').ids
            if partner_ids:
                order.message_post(
                    body=_('Purchase confirmation approval is required from group: %s') % approval.group_id.display_name,
                    partner_ids=partner_ids,
                    subtype_xmlid='mail.mt_comment',
                )

    def _approve_current_step(self):
        for order in self:
            order._sync_confirm_approval_steps()
            order.invalidate_recordset(['confirm_approval_ids'])
            current = order.confirm_approval_ids.filtered(
                lambda approval: approval.required and approval.state == 'pending'
            )[:1]

            if not current:
                return True

            if not order._user_can_approve_step(current):
                raise AccessError(_(
                    'You cannot approve this step. Required group: %s'
                ) % current.group_id.display_name)

            current.write({
                'state': 'approved',
                'approved_by_id': self.env.user.id,
                'approved_date': fields.Datetime.now(),
            })
            order.message_post(body=_('Approval step approved by %(user)s for group %(group)s.') % {
                'user': self.env.user.display_name,
                'group': current.group_id.display_name,
            })

            # Recompute and notify next group, if any.
            order._compute_confirm_approval_state()
            if order.current_approval_id:
                order._notify_current_approval_users()

        return True

    def button_confirm(self):
        orders_to_confirm = self.env['purchase.order']

        for order in self:
            if order.state not in ('draft', 'sent'):
                orders_to_confirm |= order
                continue

            order._sync_confirm_approval_steps()
            order._compute_confirm_approval_state()

            current = order.current_approval_id
            if current:
                order._approve_current_step()
                order._compute_confirm_approval_state()

                if order.current_approval_id:
                    # Still waiting for the next approval step.
                    continue

            # No rule, no lines, or all required approvals done.
            orders_to_confirm |= order

        if orders_to_confirm:
            return super(PurchaseOrder, orders_to_confirm).button_confirm()

        return True
