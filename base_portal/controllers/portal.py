# -*- coding: utf-8 -*-

from odoo.http import content_disposition, Controller, request, route
from odoo.addons.account.controllers.portal import CustomerPortal
from odoo import fields, http, SUPERUSER_ID, _
from odoo.tools import date_utils


class EmployeePortal(CustomerPortal):
    _items_per_page = 80

    @route(['/my/profile'], type='http', auth='user', website=True)
    def profile(self, redirect=None):
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        user = request.env.user
        values.update({
            'error': {},
            'error_message': [],
        })

        employee = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)])
        countries = request.env['res.country'].sudo().search([])
        states = request.env['res.country.state'].sudo().search([])

        values.update({
            'employee': employee,
            'partner': partner,
            'countries': countries,
            'states': states,
            'has_check_vat': hasattr(request.env['res.partner'], 'check_vat'),
            'partner_can_edit_vat': partner.can_edit_vat(),
            'redirect': redirect,
            'page_name': 'my_details',
        })

        response = request.render("base_portal.portal_my_employee_details", values)
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
        return response
