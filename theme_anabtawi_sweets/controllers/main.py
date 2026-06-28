# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class AnabtawiSweetsController(http.Controller):

    @http.route('/', type='http', auth='public', website=True, sitemap=True)
    def index(self, **kw):
        """
        Home page route - Anabtawi Sweets.
        """
        return request.render('theme_anabtawi_sweets.home_page_template')

    @http.route('/aboutus', type='http', auth='public', website=True, sitemap=True)
    def aboutus(self, **kw):
        """
        About Us page route.
        """
        return request.render('theme_anabtawi_sweets.about_page_template')

    @http.route('/branches', type='http', auth='public', website=True, sitemap=True)
    def branches(self, **kw):
        """
        Branches page route.
        """
        return request.render('theme_anabtawi_sweets.branches_page_template')

    @http.route('/our-catalog', type='http', auth='public', website=True, sitemap=True)
    def catalog(self, **kw):
        """
        Products Catalog page route.
        """
        return request.render('theme_anabtawi_sweets.catalog_page_template')

    @http.route('/contactus', type='http', auth='public', website=True, sitemap=True)
    def contactus(self, **kw):
        """
        Contact Us page route.
        """
        return request.render('theme_anabtawi_sweets.contact_page_template')
