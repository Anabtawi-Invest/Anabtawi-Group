from datetime import date

from odoo import api, fields, models


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

    @api.model
    def _unique_code_for(self, template_id, raw_code):
        """Build a globally unique stage code: t{template_id}_{code}."""
        raw_code = (raw_code or '').strip()
        if not template_id or not raw_code:
            return raw_code
        prefix = f't{template_id}_'
        if raw_code.startswith(prefix):
            return raw_code
        # already unique from another scheme
        if raw_code.startswith('t') and '_' in raw_code[1:]:
            return raw_code
        return f'{prefix}{raw_code}'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('issystem') and vals.get('purchase_template') and vals.get('code'):
                vals['code'] = self._unique_code_for(vals['purchase_template'], vals['code'])
        return super().create(vals_list)

    def write(self, vals):
        if 'code' in vals and not vals.get('issystem'):
            for stage in self:
                if stage.issystem:
                    continue
                template_id = vals.get('purchase_template') or stage.purchase_template.id
                if template_id:
                    vals = dict(vals)
                    vals['code'] = self._unique_code_for(template_id, vals['code'])
                    break
        res = super().write(vals)
        if 'stageusers' in vals or 'approvetype' in vals:
            self._sync_open_po_pendings()
        return res

    @api.model
    def migrate_unique_stage_codes(self):
        """One-time: rename duplicate stage codes and remap open/done PO states.

        Run from shell after deploy:
            env['tanmya.purchase.stage'].migrate_unique_stage_codes()
            env.cr.commit()
        """
        Stage = self.sudo()
        Pending = self.env['tanmya.purchase.order.pending'].sudo()
        PO = self.env['purchase.order'].sudo()
        system_codes = set(Stage.search([('issystem', '=', True)]).mapped('code'))
        migrated = []

        for stage in Stage.search([('issystem', '=', False), ('purchase_template', '!=', False)]):
            old_code = stage.code
            new_code = self._unique_code_for(stage.purchase_template.id, old_code)
            if old_code == new_code:
                continue
            # conflict: new_code already used by another stage
            conflict = Stage.search([('code', '=', new_code), ('id', '!=', stage.id)], limit=1)
            if conflict:
                new_code = f't{stage.purchase_template.id}_s{stage.id}'

            template = stage.purchase_template
            # Remap POs of this type still on the old short code
            pos = PO.search([
                ('purchasetype', '=', template.id),
                ('state', '=', old_code),
            ])
            if pos:
                pos.write({'state': new_code})

            pendings = Pending.search([
                ('state', '=', old_code),
                ('purchaseorder.purchasetype', '=', template.id),
            ])
            if pendings:
                pendings.write({'state': new_code})

            # bypass write() code mangling / sync during rename
            self.env.cr.execute(
                'UPDATE tanmya_purchase_stage SET code = %s WHERE id = %s',
                (new_code, stage.id),
            )
            migrated.append((stage.id, old_code, new_code, len(pos), len(pendings)))

        Stage.invalidate_model(['code'])
        return migrated

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
