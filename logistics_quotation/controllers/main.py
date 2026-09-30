# -*- coding: utf-8 -*-
import base64
from odoo import http, _
from odoo.http import request


class LogisticsPortalController(http.Controller):

    @http.route('/logistics/rfq/submit/<string:token>', type='http', auth='public', website=True, csrf=True)
    def logistics_rfq_submit_page(self, token, **kw):
        invitation = request.env['logistics.request.invitation'].sudo().search([('token', '=', token)], limit=1)
        if not invitation:
            return request.render('logistics_quotation.portal_invalid_token_template', {})

        logistics_request = invitation.request_id
        values = {
            'invitation': invitation,
            'request': logistics_request,
            'company': logistics_request.company_id,
            'items': logistics_request.item_ids,
            'already_submitted': invitation.state == 'submitted',
        }
        return request.render('logistics_quotation.portal_rfq_submit_template', values)

    @http.route('/logistics/rfq/submit/<string:token>/post', type='http', auth='public', methods=['POST'], website=True, csrf=True)
    def logistics_rfq_submit_post(self, token, **post):
        invitation = request.env['logistics.request.invitation'].sudo().search([('token', '=', token)], limit=1)
        if not invitation:
            return request.render('logistics_quotation.portal_invalid_token_template', {})

        logistics_request = invitation.request_id
        partner = invitation.partner_id

        price_subtotal = float(post.get('price_subtotal') or 0.0)
        handling_fee = float(post.get('handling_fee') or 0.0)
        transit_time_days = int(post.get('transit_time_days') or 0)
        notes = post.get('notes') or ''

        # File upload handling
        quote_file = request.httprequest.files.get('quote_file')
        file_content = False
        filename = False
        if quote_file and quote_file.filename:
            filename = quote_file.filename
            file_content = base64.b64encode(quote_file.read())

        # Check or create quote line
        quote_line = invitation.quote_line_id
        line_vals = {
            'request_id': logistics_request.id,
            'partner_id': partner.id,
            'price_subtotal': price_subtotal,
            'handling_fee': handling_fee,
            'transit_time_days': transit_time_days,
            'notes': notes,
        }
        if file_content:
            line_vals.update({
                'quote_attachment': file_content,
                'quote_filename': filename,
            })

        if quote_line:
            quote_line.sudo().write(line_vals)
        else:
            quote_line = request.env['logistics.request.line'].sudo().create(line_vals)

        # Update invitation tracker
        invitation.sudo().write({
            'state': 'submitted',
            'submitted_date': request.env['fields'].Datetime.now(),
            'quote_line_id': quote_line.id,
        })

        # Update logistics request status if draft or rfq
        if logistics_request.state in ('draft', 'rfq'):
            logistics_request.sudo().write({'state': 'quoted'})

        # Post chatter notification
        logistics_request.sudo().message_post(
            body=_(
                "Forwarder <b>%s</b> submitted quotation via Web Portal.<br/> Freight: %s | Handling: %s | Transit: %s Days.",
                partner.display_name,
                price_subtotal,
                handling_fee,
                transit_time_days,
            )
        )

        return request.redirect('/logistics/rfq/thanks')

    @http.route('/logistics/rfq/thanks', type='http', auth='public', website=True)
    def logistics_rfq_thanks(self, **kw):
        return request.render('logistics_quotation.portal_rfq_thanks_template', {})
