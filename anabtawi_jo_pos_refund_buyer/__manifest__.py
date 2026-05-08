# Part of Anabtawi Group customizations. See models docstring.
{
    'name': 'Jordan PoS refund buyer match (JoFotara)',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localizations',
    'summary': 'Align UBL buyer data on POS credit notes with original sales for JoFotara',
    'description': """
When creating a POS refund, the standard Jordan localization can omit buyer fields in the
UBL that were present on the original sale. JoFotara then rejects the credit with:
"Credit invoice buyer info does not match the original invoice".

This module emits the same customer party structure on refunds as on sales (full party,
address, contact) while leaving the rest of l10n_jo_edi_pos unchanged.
    """,
    'depends': ['l10n_jo_edi_pos'],
    'author': 'Anabtawi Group',
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}
