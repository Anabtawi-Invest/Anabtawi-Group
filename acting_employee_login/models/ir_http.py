# -*- coding: utf-8 -*-

from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _pre_dispatch(cls, rule, args):
        super()._pre_dispatch(rule, args)
        cls._inject_acting_employee_context()

    @classmethod
    def _inject_acting_employee_context(cls):
        if not request or not getattr(request, 'session', None):
            return
        if not request.session.uid:
            return
        acting_id = request.session.get('acting_employee_id')
        branch_access_id = request.session.get('acting_branch_access_id')
        if not acting_id and not branch_access_id:
            return
        request.update_context(
            acting_employee_id=acting_id,
            acting_employee_name=request.session.get('acting_employee_name') or '',
            acting_branch_access_id=branch_access_id,
            acting_branch_name=request.session.get('acting_branch_name') or '',
        )

    @classmethod
    def _post_logout(cls):
        if request and getattr(request, 'session', None):
            request.session.pop('acting_employee_id', None)
            request.session.pop('acting_employee_name', None)
            request.session.pop('acting_branch_access_id', None)
            request.session.pop('acting_branch_name', None)
        super()._post_logout()
