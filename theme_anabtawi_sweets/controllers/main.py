# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class AnabtawiSweetsController(http.Controller):

    @http.route('/aboutus', type='http', auth='public', website=True, sitemap=True)
    def aboutus(self, **kw):
        return request.render('theme_anabtawi_sweets.aboutus_template')

    @http.route('/branches', type='http', auth='public', website=True, sitemap=True)
    def branches(self, **kw):
        return request.render('theme_anabtawi_sweets.branches_template')

    @http.route('/our-catalog', type='http', auth='public', website=True, sitemap=True)
    def catalog(self, **kw):
        return request.render('theme_anabtawi_sweets.catalog_template')

    @http.route('/contactus', type='http', auth='public', website=True, sitemap=True)
    def contactus(self, **kw):
        return request.render('theme_anabtawi_sweets.contact_template')
