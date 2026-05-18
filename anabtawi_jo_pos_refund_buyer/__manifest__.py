# Part of Anabtawi Group customizations. See models docstring.
{
    'name': 'Jordan PoS JoFotara fixes (buyer + discount)',
    'version': '19.0.1.1.0',
    'category': 'Accounting/Localizations',
    'summary': 'JoFotara POS: buyer match on refunds + non-negative line/discount allowances',
    'description': """
Fixes Jordan POS e-invoicing rejections seen on JoFotara:

1) Credit notes / refunds: buyer UBL blocks must match the original sale ("buyer info
   does not match the original invoice").

2) generalInvoiceCalculations "discount cannot be negative": derive line AllowanceCharge
   amounts with abs(), like l10n_jo_edi on account.move, avoiding negative micro-discounts
   from rounding with fractional weighed quantities while Disc.% is zero.
    """,
    'depends': ['l10n_jo_edi_pos'],
    'author': 'Anabtawi Group',
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}
