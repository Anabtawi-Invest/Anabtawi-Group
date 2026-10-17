from datetime import date

from odoo import fields, models


class tanmya_PurchaseStage(models.Model):
    _name = "tanmya.purchase.stage"
    code = fields.Char(string='Stage code', required=True)
    name = fields.Char(string='Stage name', required=True)
    stageusers = fields.Many2many('res.users', string='Related users')
    purchase_template = fields.Many2one('tanmya.purchase.stage.type', string='Purchase template', required=False)
    stageorder = fields.Integer(string='Stage Rank', required=True)
    _sql_constraints = [
        ('tanmya_stage_code_unique', 'unique(code)', 'stage code already exists!')
    ]
    issystem = fields.Boolean(string='internal', default=False, invisible=True)
    approvetype = fields.Selection([
        ('sequence', 'sequence'),
        ('anyone', 'anyone'),
        ('parallel', 'parallel'),
    ], string='Approve Mode', default='sequence')

    def write(self, vals):
        res = super().write(vals)
        if 'stageusers' in vals or 'approvetype' in vals:
            self._sync_open_po_pendings()
        return res

    def _sync_open_po_pendings(self):
        """Align open PO pending rows with current stage users.

        Adding a user to a stage creates a waiting pending (Approve button)
        on POs already on that stage.
        """
        Pending = self.env['tanmya.purchase.order.pending']
        Activity = self.env['mail.activity'].sudo()
        PurchaseOrder = self.env['purchase.order']
        skip_states = {'draft', 'sent', 'purchase', 'done', 'cancel'}
        model_id = self.env['ir.model']._get_id('purchase.order')

        for stage in self:
            if not stage.code or stage.issystem:
                continue
            domain = [
                ('state', '=', stage.code),
                ('state', 'not in', list(skip_states)),
            ]
            if stage.purchase_template:
                domain.append(('purchasetype', '=', stage.purchase_template.id))
            orders = PurchaseOrder.search(domain)
            if not orders:
                continue

            wanted = stage.stageusers
            for po in orders:
                current = Pending.search([
                    ('purchaseorder', '=', po.id),
                    ('state', '=', po.state),
                ])
                approved_users = current.filtered(lambda p: p.status == 'approve').mapped('user')
                stale = current.filtered(
                    lambda p: p.status in ('waiting', 'queue') and p.user not in wanted
                )
                if stale:
                    stale.write({'status': 'decline'})

                if stage.approvetype in ('anyone', 'parallel'):
                    for user in wanted:
                        if user in approved_users:
                            continue
                        rec = current.filtered(lambda p, u=user: p.user == u)[:1]
                        if rec:
                            if rec.status != 'waiting':
                                rec.write({'status': 'waiting'})
                        else:
                            Pending.create({
                                'user': user.id,
                                'purchaseorder': po.id,
                                'state': po.state,
                                'status': 'waiting',
                                'userorder': 0,
                            })
                        self._ensure_approve_activity(Activity, model_id, po, user)
                else:
                    self.env.cr.execute("""
                        SELECT res_users_id
                        FROM res_users_tanmya_purchase_stage_rel
                        WHERE tanmya_purchase_stage_id = %s
                        ORDER BY seq
                    """, (stage.id,))
                    ordered_uids = [row[0] for row in self.env.cr.fetchall()]
                    remaining = [uid for uid in ordered_uids if uid not in approved_users.ids]
                    for index, uid in enumerate(remaining, start=1):
                        status = 'waiting' if index == 1 else 'queue'
                        user = self.env['res.users'].browse(uid)
                        rec = current.filtered(lambda p, u=uid: p.user.id == u)[:1]
                        if rec:
                            if rec.status != status or rec.userorder != index:
                                rec.write({'status': status, 'userorder': index})
                        else:
                            Pending.create({
                                'user': uid,
                                'purchaseorder': po.id,
                                'state': po.state,
                                'status': status,
                                'userorder': index,
                            })
                        if status == 'waiting':
                            self._ensure_approve_activity(Activity, model_id, po, user)

    def _ensure_approve_activity(self, activity_model, model_id, po, user):
        has_act = activity_model.search_count([
            ('res_model', '=', 'purchase.order'),
            ('res_id', '=', po.id),
            ('user_id', '=', user.id),
            ('activity_type_id', '=', 4),
        ])
        if not has_act:
            activity_model.create({
                'activity_type_id': 4,
                'date_deadline': date.today(),
                'summary': 'Request to approve',
                'user_id': user.id,
                'res_model_id': model_id,
                'res_id': po.id,
            })
