from odoo import api, fields, models


class CakeSendEmailWizard(models.TransientModel):
    _name = 'cake.send.email.wizard'
    _description = 'Send Cake Order to Manufacturing by Email'

    cake_order_id = fields.Many2one('cake.order', required=True, readonly=True)
    email_to      = fields.Char('To | إلى', required=True)
    email_cc      = fields.Char('CC | نسخة')
    subject       = fields.Char('Subject | الموضوع', required=True)
    body_html     = fields.Html('Body | المحتوى', sanitize=False)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order_id = self.env.context.get('default_cake_order_id')
        if order_id:
            order = self.env['cake.order'].browse(order_id)
            cfg = self.env['cake.config'].search([], limit=1)
            subj = (cfg.email_subject_template or 'Custom Cake Order #{ref}').replace(
                '{ref}', order.name).replace('{persons}', order.persons or '')
            res.update({
                'cake_order_id': order.id,
                'email_to':  cfg.manufacturing_email or '',
                'subject':   subj,
                'body_html': order._build_html_spec(),
            })
        return res

    def action_send(self):
        self.ensure_one()
        self.env['mail.mail'].sudo().create({
            'subject':   self.subject,
            'email_to':  self.email_to,
            'email_cc':  self.email_cc or '',
            'body_html': self.body_html,
        }).send()
        self.cake_order_id.write({'email_sent': True})
        self.cake_order_id.message_post(
            body=f'📧 Email sent to: {self.email_to}',
            message_type='notification',
        )
        return {'type': 'ir.actions.act_window_close'}
