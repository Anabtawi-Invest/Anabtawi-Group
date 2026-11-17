# -*- coding: utf-8 -*-
from odoo import http
from odoo.addons.website_hr_recruitment.controllers.main import WebsiteHrRecruitment


class AnabtawiWebsiteHrRecruitment(WebsiteHrRecruitment):

    @http.route([
        '/jobs',
        '/jobs/page/<int:page>',
    ], type='http', auth="public", website=True, sitemap=WebsiteHrRecruitment.sitemap_jobs)
    def jobs(self, **kwargs):
        response = super().jobs(**kwargs)
        if hasattr(response, 'qcontext') and 'jobs' in response.qcontext:
            jobs = response.qcontext['jobs'].filtered(lambda j: j.is_published and j.active)
            response.qcontext['jobs'] = jobs
            if not jobs:
                response.qcontext['search_count'] = 0
        return response

