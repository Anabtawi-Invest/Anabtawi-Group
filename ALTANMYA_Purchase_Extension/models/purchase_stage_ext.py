from odoo import api, fields, models, tools
from datetime import date, datetime,timedelta



class TanmyaPurchaseExt(models.Model):
    _inherit = 'purchase.order'


    purchasetype =fields.Many2one('tanmya.purchase.stage.type',string='Purchase type',compute='_calc_stage',
                                  inverse='_get_type', tracking=3,
                                  store=True)
    state = fields.Selection(selection=lambda self: self.get_stages(), string='Status',
                             readonly=True, copy=False, index=True, tracking=3, default='draft'
                             )
    showpending=fields.Boolean(string='pending status',compute='_show_pending_status',
                               depends=['state'],store=False)

    userisadmin = fields.Boolean(compute='_check_admin',default=True)

    def _check_admin(self):
    #     ret=False
    #     qquery = """ SELECT res_groups_users_rel.*
	# FROM ir_module_category inner join res_groups  on res_groups.category_id=ir_module_category.id
	# inner join  res_groups_users_rel on res_groups_users_rel.gid=res_groups.id
	# where ir_module_category.name='Purchase' and res_groups.name='Administrator' and res_groups_users_rel.uid="""\
    #              + str(self.env.uid)
    #     self.env.cr.execute(qquery)
    #     auth_usr = self.env.cr.fetchall()
    #     if auth_usr:
    #         # print(str(self.env.uid))
    #         ret= True
        ret=False
        if self.state in ('draft','sent'):
            ret=True
        elif self.state in ('purchase','done'):
            ret=False
        else:
            user0 = self.env['res.users'].browse(self.env.uid)
            ret=user0.has_group('ALTANMYA_Purchase_Extension.altanmya_purchase_stage_type')
        # ret=self.env.uid.has_group('purchase.group_purchase_manager')
        self.userisadmin=ret


    def _get_type(self):
        ret=False
        if self.state in ('draft', 'sent','purchase','done'):
            pass
        else:
            user0 = self.env['res.users'].browse(self.env.uid)
            ret=user0.has_group('ALTANMYA_Purchase_Extension.altanmya_purchase_stage_type')
        if ret:
            self._change_type()


    def _change_type(self):
        self.env['tanmya.purchase.order.pending'].search([('user', '=', self.env.uid)
                                                                   , ('purchaseorder', '=', self.id)]
                                                                  ).unlink()
        for act in self.activity_ids:
            if act.activity_type_id.id == 4 and act.res_id == self.id :
                act.action_feedback('Request is changed')
        self.state='sent'
        rec_id = self.env['ir.model'].sudo().search([('model', '=', 'purchase.order')], limit=1)
        if self.user_id:
            self.env['mail.activity'].sudo().create({
                'activity_type_id': 4,
                'date_deadline': date.today(),
                'summary': 'pruchase type stage has changed',
                'user_id': self.user_id.id,
                'res_model_id': rec_id.id,
                'res_id': self.id
            })
        self.process_stages()

    @api.depends('amount_total', 'currency_id')
    def _calc_stage(self):
        # aux=self.purchasetype
        # if self.state in ('draft','sent') and aux:
        #     self.purchasetype=aux
        # else:
            tot =0
            currid=0
            for rec in self:
                tot +=rec.amount_total
                currid=rec.currency_id.id

            ret_type= self.env['tanmya.purchase.stage.type'].search([('currency','=',currid),
                                                           ('minrange','<=',tot),
                                                           ('maxrange','>=',tot)],limit=1)
            if not ret_type:
                ret_type = self.env['tanmya.purchase.stage.type'].search([('currency','=',False),('minrange', '<=', tot),
                                                                          ('maxrange', '>=', tot)], limit=1)
            self.purchasetype=ret_type





    def get_stages(self):
        lst=[]
        recset=self.env['tanmya.purchase.stage'].search([],order = 'stageorder')
        for stg in recset:
            lst.append((stg.code,stg.name))
        return lst



    def button_confirm(self):
        if self.purchasetype:
            if self.state in ('draft','sent'):
                newlist = sorted(self.purchasetype.stages, key=lambda x: x.stageorder)
                self.state=newlist[0].code
                self.process_stages()
        else:
            super(TanmyaPurchaseExt,self).button_confirm()

    def _show_pending_status(self):
        ret=False
        if self.purchasetype:
            if self.state in self.purchasetype.get_stage_list():

               if self.env['tanmya.purchase.order.pending'].search_count([('user','=',self.env.uid)
                                                                   ,('state','=',self.state)
                                                                   ,('purchaseorder','=',self.id)
                                                                   ,('status','=','waiting')]):
                   ret=True
        #            print('okakak')
        # print('done')
        # print(ret)
        self.showpending= ret



    def action_approve(self):
      rec=  self.env['tanmya.purchase.order.pending'].search([
          ('user', '=', self.env.uid)
          , ('state', '=', self.state)
          , ('purchaseorder', '=', self.id)
          , ('status', '=', 'waiting')
           ], limit=1)
      if rec:
          # print('oldstate')
          # print(self.state)
          oldstate=self.state

          rec.update({'status': 'approve'})

          for act in self.activity_ids:
              if act.activity_type_id.id==4 and act.res_id==self.id and act.user_id.id==self.env.uid:
                  act.action_feedback('Request is approved')
                  # print('approved')
          self.check_stage()
          # print('newstate')
          # print(self.state)
          current_stage=self.env['tanmya.purchase.stage'].sudo().search([('code','=',self.state)],limit=1)
          if current_stage.approvetype=='sequence' and oldstate==self.state:
                rec_next=self.env['tanmya.purchase.order.pending'].search([('state', '=', self.state)
                                                               , ('purchaseorder', '=', self.id)
                                                               , ('status', '=', 'queue')]
                                                                ,order = 'userorder'
                                                                 , limit=1)
                rec_next[0].update({'status': 'waiting'})
                rec_id = self.env['ir.model'].sudo().search([('model', '=', 'purchase.order')], limit=1)
                self.env['mail.activity'].sudo().create({
                    'activity_type_id': 4,
                    'date_deadline': date.today() ,
                    'summary': 'Request to approve',
                    'user_id': rec_next.user.id,
                    'res_model_id': rec_id.id,
                    'res_id': self.id
                })


    def action_decline(self):
        rec = self.env['tanmya.purchase.order.pending'].search([
            ('user', '=', self.env.uid)
            , ('state', '=', self.state)
            , ('purchaseorder', '=', self.id)
            , ('status', '=', 'waiting')
        ], limit=1)
        if rec:
            rec[0].update({'status': 'decline'})
            self.state='sent'
            super(TanmyaPurchaseExt, self).button_cancel()



    def check_stage(self):

        count_approve=self.env['tanmya.purchase.order.pending'].search_count([('state', '=', self.state)
                                                               , ('purchaseorder', '=', self.id)
                                                               , ('status', '=', 'approve')])
        current_stage = self.env['tanmya.purchase.stage'].sudo().search([('code', '=', self.state)], limit=1)
        newlist = sorted(self.purchasetype.stages, key=lambda x: x.stageorder)

        if current_stage.approvetype == 'anyone':
            if current_stage.code == newlist[len(newlist) - 1].code:
                self.state = 'sent'
                super(TanmyaPurchaseExt, self).button_confirm()
            else:
                for x in range(0, len(newlist) - 1):
                    if newlist[x].code == current_stage.code:
                        self.state = newlist[x + 1].code
                        self.process_stages()
                        break

        if len(current_stage.stageusers)==count_approve:
              if current_stage.code == newlist[len(newlist) - 1].code:
                  self.state='sent'
                  super(TanmyaPurchaseExt, self).button_confirm()
              else:
                  for x in range(0, len(newlist) - 1):
                        if newlist[x].code==current_stage.code:
                            self.state=newlist[x+1].code
                            self.process_stages()
                            break



    def process_stages(self):
        current_stage = self.env['tanmya.purchase.stage'].sudo().search([('code', '=', self.state)], limit=1)
        uorder = 0
        rec_id=self.env['ir.model'].sudo().search([('model','=','purchase.order')], limit=1)
       # print(rec_id)
        qquery=" select seq,res_users_id  from res_users_tanmya_purchase_stage_rel  where tanmya_purchase_stage_id=" + str(current_stage.id) + " order by seq"
        self.env.cr.execute(qquery)
        stage_users=self.env.cr.fetchall()
      #  print(stage_users)
        for usrs in stage_users: # current_stage.stageusers:
                    if current_stage.approvetype=='parallel' or current_stage.approvetype=='anyone':
                        self.env['tanmya.purchase.order.pending'].create({
                            'user': usrs[1],
                            'purchaseorder':self.id,
                            'state':self.state,
                            'userorder':0
                        })
                        self.env['mail.activity'].sudo().create({
                            'activity_type_id': 4,
                            'date_deadline': date.today() ,
                            'summary': 'Request to approve',
                            'user_id': usrs[1],
                            'res_model_id': rec_id.id,
                            'res_id': self.id
                        })
                    else:
                        uorder = uorder+1
                        if uorder==1:
                            self.env['tanmya.purchase.order.pending'].create({
                                'user': usrs[1],
                                'purchaseorder':self.id,
                                'state':self.state,
                                'status': 'waiting',
                                'userorder' :uorder
                            })
                            self.env['mail.activity'].sudo().create({
                                'activity_type_id': 4,
                                'date_deadline': date.today() ,
                                'summary': 'Request to approve',
                                'user_id': usrs[1],
                                'res_model_id': rec_id.id,
                                'res_id': self.id
                            })
                        else:
                            self.env['tanmya.purchase.order.pending'].create({
                                'user': usrs[1],
                                'purchaseorder':self.id,
                                'state':self.state,
                                'status':'queue',
                                'userorder': uorder
                            })





    @api.model
    def create(self, vals_list):
       res = super(TanmyaPurchaseExt, self).create(vals_list)
       return res

    def write(self,vals):
        if 'purchasetype' in vals:
            newval=vals['purchasetype']
            oldval=self.purchasetype

            if self.state in ('purchase','done'):
                vals['purchasetype']=oldval
        res = super(TanmyaPurchaseExt, self).write( vals)
        return res
