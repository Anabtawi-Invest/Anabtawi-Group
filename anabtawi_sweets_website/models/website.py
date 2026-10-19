# -*- coding: utf-8 -*-
from odoo import models
from odoo.http import request
from odoo.tools.urls import _contains_dot_segments


class Website(models.Model):
    _inherit = "website"

    def _get_canonical_url(self):
        """Avoid crashing error pages when the request path has '.' / '..' segments.

        Odoo 19 forbids dot segments in urljoin. Scanners often hit paths like
        '/../admin' or '/./', which then break website error-page rendering.
        """
        self.ensure_one()
        url = request.httprequest.path if request else "/"
        if url == self.homepage_url:
            url = "/"
        if _contains_dot_segments(url):
            url = "/"
        try:
            return self.env["ir.http"]._url_localized(
                url=url,
                lang_code=request.lang.code,
                canonical_domain=self.get_base_url(),
            )
        except ValueError:
            # Fallback: never break layout/error rendering because of a bad URL.
            return self.get_base_url().rstrip("/") + "/"

    def _is_canonical_url(self):
        try:
            return super()._is_canonical_url()
        except ValueError:
            return False
