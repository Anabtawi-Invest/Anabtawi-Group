# -*- coding: utf-8 -*-
import re

from odoo import api, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _normalize_phone(self, phone):
        if not phone:
            return ''
        return re.sub(r'\D', '', phone.strip())

    @api.model
    def _phone_search_field(self):
        if 'phone_mobile_search' in self._fields:
            return 'phone_mobile_search'
        return 'phone'

    @api.model
    def find_or_create_by_phone(self, phone, company, name=None):
        normalized = self._normalize_phone(phone)
        if len(normalized) < 7:
            return self.env['res.partner']

        search_field = self._phone_search_field()
        search_value = normalized[-9:] if len(normalized) >= 9 else normalized
        partner = self.sudo().search([
            ('company_id', 'in', [False, company.id]),
            (search_field, 'ilike', search_value),
        ], limit=1)

        display_name = (name or '').strip() or phone
        if not partner:
            return self.sudo().create({
                'name': display_name,
                'phone': phone,
                'company_id': company.id,
            })

        vals = {}
        partner_phone = self._normalize_phone(partner.phone)
        if name and partner.name in (partner.phone, partner_phone, normalized, phone):
            vals['name'] = display_name
        if not partner.phone:
            vals['phone'] = phone
        if vals:
            partner.sudo().write(vals)
        return partner
