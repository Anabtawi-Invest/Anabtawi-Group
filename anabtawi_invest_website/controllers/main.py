# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

class AnabtawiInvestController(http.Controller):

    @http.route('/', type='http', auth='public', website=True, sitemap=True)
    def index(self, **kw):
        """
        Home page route.
        Renders the premium Rolex-inspired hero and Hikma-style portfolio overview.
        """
        return request.render('anabtawi_invest_website.home_page_template')

    @http.route('/about-invest', type='http', auth='public', website=True, sitemap=True)
    def about_invest(self, **kw):
        """
        About Us and Corporate Portfolio route.
        Renders detailed corporate legacy, investment philosophy, and assets list.
        """
        return request.render('anabtawi_invest_website.about_page_template')
