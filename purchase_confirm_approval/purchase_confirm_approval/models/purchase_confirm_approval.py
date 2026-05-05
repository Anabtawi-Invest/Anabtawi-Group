# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PurchaseConfirmApprovalRule(models.Model):
    _name = 'purchase.confirm.approval.rule'
    _description = 'Purchase Confirm Approval Rule'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, id'

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)
    sequence = fields.Integer(default=10, tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        tracking=True,
        help='Leave empty to apply to all companies.',
    )
    line_ids = fields.One2many(
        'purchase.confirm.approval.rule.line',
        'rule_id',
        string='Approval Steps',
        copy=True,
    )

    _sql_constraints = [
        ('name_company_unique', 'unique(name, company_id)', 'The rule name must be unique per company.'),
    ]

    @api.model
    def _get_rule_for_order(self, order):
        """Return the first active rule applicable to this purchase order."""
        domain = [('active', '=', True), '|', ('company_id', '=', False), ('company_id', '=', order.company_id.id)]
        return self.search(domain, order='company_id desc, sequence asc, id asc', limit=1)


class PurchaseConfirmApprovalRuleLine(models.Model):
    _name = 'purchase.confirm.approval.rule.line'
    _description = 'Purchase Confirm Approval Rule Line'
    _order = 'sequence, id'

    rule_id = fields.Many2one(
        'purchase.confirm.approval.rule',
        required=True,
        ondelete='cascade',
    )
    active = fields.Boolean(default=True)
    sequence = fields.Integer(required=True, default=10)
    name = fields.Char(required=True)
    required = fields.Boolean(default=True)
    group_id = fields.Many2one(
        'res.groups',
        string='Approval Group',
        required=True,
        help='Users in this group can approve this step.',
    )
    specific_user_ids = fields.Many2many(
        'res.users',
        'purchase_confirm_approval_line_user_rel',
        'line_id',
        'user_id',
        string='Specific Users',
        help='Optional. If set, only these users can approve this step. They should also belong to the selected group.',
    )
    user_to_notify_ids = fields.Many2many(
        'res.users',
        'purchase_confirm_approval_line_notify_user_rel',
        'line_id',
        'user_id',
        string='Users to Notify',
    )
    exclusive_approval = fields.Boolean(
        default=True,
        help='If enabled, a user who approved an earlier step cannot approve this step on the same RFQ/PO.',
    )

    @api.constrains('specific_user_ids', 'group_id')
    def _check_specific_users_in_group(self):
        for line in self:
            if line.specific_user_ids and line.group_id:
                invalid_users = line.specific_user_ids.filtered(lambda user: line.group_id not in user.group_ids)
                if invalid_users:
                    raise ValidationError(_(
                        'These specific users are not members of the approval group "%(group)s": %(users)s'
                    ) % {
                        'group': line.group_id.display_name,
                        'users': ', '.join(invalid_users.mapped('display_name')),
                    })


class PurchaseConfirmApproval(models.Model):
    _name = 'purchase.confirm.approval'
    _description = 'Purchase Confirmation Approval'
    _inherit = ['mail.thread']
    _order = 'order_id, sequence, id'

    order_id = fields.Many2one(
        'purchase.order',
        required=True,
        ondelete='cascade',
        index=True,
    )
    rule_id = fields.Many2one('purchase.confirm.approval.rule', required=True, ondelete='restrict')
    line_id = fields.Many2one('purchase.confirm.approval.rule.line', required=True, ondelete='restrict')
    sequence = fields.Integer(related='line_id.sequence', store=True)
    required = fields.Boolean(related='line_id.required', store=True)
    group_id = fields.Many2one(related='line_id.group_id', store=True)
    state = fields.Selection(
        [('pending', 'Pending'), ('approved', 'Approved'), ('skipped', 'Skipped')],
        default='pending',
        required=True,
        tracking=True,
    )
    approved_by_id = fields.Many2one('res.users', readonly=True, tracking=True)
    approved_date = fields.Datetime(readonly=True, tracking=True)

    _sql_constraints = [
        ('order_line_unique', 'unique(order_id, line_id)', 'Each approval step can only exist once per purchase order.'),
    ]

    def action_approve(self):
        for approval in self:
            approval.order_id._approve_current_step()
        return True
