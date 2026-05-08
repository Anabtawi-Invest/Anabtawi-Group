# -*- coding: utf-8 -*-
"""JoFotara: POS refund XML must repeat the same buyer block as the original order.

Standard l10n_jo_edi_pos strips several AccountingCustomerParty fields on credit_note
documents. The portal compares buyer info to the original submission and responds with
EINV_MESSAGE "Credit invoice buyer info does not match the original invoice".
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
