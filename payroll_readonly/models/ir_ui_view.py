from odoo import models

from .base import OFFICER_XMLID, READONLY_XMLID


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    def _postprocess_view(self, node, model_name, editable=True, node_info=None, **options):
        # Show payroll fields that the view reserved for Officer. Buttons keep
        # their original group, so Compute, Confirm, and similar actions stay hidden.
        nodes = [node] if node.get('groups') else []
        nodes.extend(node.xpath('//*[@groups]'))
        for element in nodes:
            if element.tag == 'button':
                continue
            updated = _extend_groups(element.get('groups'))
            if updated:
                element.set('groups', updated)
        return super()._postprocess_view(
            node, model_name, editable=editable, node_info=node_info, **options,
        )


def _extend_groups(groups):
    parts = [part.strip() for part in (groups or '').split(',') if part.strip()]
    tokens = {part.lstrip('!') for part in parts}
    if OFFICER_XMLID not in tokens or READONLY_XMLID in tokens:
        return None
    parts.append(READONLY_XMLID)
    return ','.join(parts)
