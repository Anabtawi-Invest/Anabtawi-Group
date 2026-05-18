# -*- coding: utf-8 -*-
"""JoFotara Jordan POS XML fixes (Anabtawi Group):

1. Refunds: buyer node must mirror the original sale or JoFotara returns
   "Credit invoice buyer info does not match the original invoice".

2. Line discount amounts: Jordan account EDI uses abs() per line on AllowanceCharge; POS
   does not. Sub-cent rounding with fractional quantities can make the derived discount
   negative while Disc.% is zero. JoFotara rejects with generalInvoiceCalculations
   "discount cannot be negative". We emit abs() on line allowances (matching account Move).
"""

from odoo import models


class PosEdiXmlUBL21Jo(models.AbstractModel):
    _inherit = 'pos.edi.xml.ubl_21.jo'

    def _add_pos_order_accounting_customer_party_nodes(self, document_node, vals):
        super()._add_pos_order_accounting_customer_party_nodes(document_node, vals)
        document_node['cac:AccountingCustomerParty'].update({
            'cac:AccountingContact': {
                'cbc:Telephone': {'_text': self._sanitize_phone(vals['customer'].phone)},
            },
        })

    def _get_party_node(self, vals):
        partner = vals['partner']
        commercial_partner = partner.commercial_partner_id
        is_customer = vals['role'] == 'customer'
        vat = commercial_partner.vat or ''
        return {
            'cac:PartyIdentification': {
                'cbc:ID': {
                    '_text': vat,
                    'schemeID': 'TN' if partner.country_code == 'JO' else 'PN',
                },
            } if is_customer else None,
            'cac:PostalAddress': self._get_address_node(vals),
            'cac:PartyTaxScheme': {
                'cbc:CompanyID': {'_text': vat},
                'cac:TaxScheme': {
                    'cbc:ID': {'_text': 'VAT'},
                },
            },
            'cac:PartyLegalEntity': {
                'cbc:RegistrationName': {'_text': commercial_partner.name},
            },
        }

    def _get_address_node(self, vals):
        partner = vals['partner']
        country = partner.country_id
        state = partner.state_id

        return {
            'cbc:PostalZone': {'_text': partner.zip or ''},
            'cbc:CountrySubentityCode': {'_text': state.code if state else ''},
            'cac:Country': {
                'cbc:IdentificationCode': {'_text': country.code if country else ''},
            },
        }

    def _add_pos_order_line_allowance_charge_nodes(self, line_node, vals):
        """Mirror l10n_jo_edi (account invoices): allowance amount is never negative."""
        currency_suffix = vals['currency_suffix']
        amount = abs(vals[f'discount_amount{currency_suffix}'])
        line_node['cac:Price']['cac:AllowanceCharge'] = {
            'cbc:ChargeIndicator': {'_text': 'false'},
            'cbc:AllowanceChargeReason': {'_text': 'DISCOUNT'},
            'cbc:Amount': {
                '_text': self.format_float(amount, vals['currency_dp']),
                'currencyID': vals['currency_name'],
            },
        }

    def _add_pos_order_allowance_charge_nodes(self, document_node, vals):
        """Ensure document-level recap discount is never negative (same edge cases)."""
        currency_suffix = vals['currency_suffix']
        raw = vals[f'discount_amount{currency_suffix}']
        amount = abs(raw)
        document_node['cac:AllowanceCharge'] = {
            'cbc:ChargeIndicator': {'_text': 'false'},
            'cbc:AllowanceChargeReason': {'_text': 'discount'},
            'cbc:Amount': {
                '_text': self.format_float(amount, vals['currency_dp']),
                'currencyID': vals['currency_name'],
            },
        }
