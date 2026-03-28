import logging
import traceback

from odoo import models

_logger = logging.getLogger(__name__)


class HrLeaveAllocationDebug(models.Model):
    _inherit = "hr.leave.allocation"

    def unlink(self):
        linked_slots = self.env["planning.slot"].sudo().search([
            ("ot_generated_leave_id", "in", self.ids),
        ])
        _logger.warning(
            (
                "[planning_enhancement][allocation_unlink] attempt_ids=%s linked_slot_ids=%s "
                "linked_slot_names=%s traceback=%s"
            ),
            self.ids,
            linked_slots.ids,
            linked_slots.mapped("name"),
            "".join(traceback.format_stack(limit=20)),
        )
        return super().unlink()
