from odoo import Command

from .common import ApprovalMatrixCase


class TestTaskDuplication(ApprovalMatrixCase):
    def test_task_copy_preserves_route_and_resets_decisions(self):
        task = self._new_task(allocation_value=2.0, allocation_unit="days")
        lines = self._add_route(task)
        task.action_submit_for_approval()
        task.with_user(self.approver_1).action_approve()
        copied = task.copy()
        self.assertTrue(copied.approval_required)
        self.assertEqual(copied.approval_type, task.approval_type)
        self.assertEqual(copied.approval_state, "draft")
        self.assertEqual(
            copied.approval_line_ids.mapped("approver_id"),
            lines.mapped("approver_id"),
        )
        self.assertEqual(set(copied.approval_line_ids.mapped("state")), {"waiting"})
        self.assertFalse(any(copied.approval_line_ids.mapped("decision_date")))
        self.assertFalse(self._linked_activities(copied))
        self.assertEqual(copied.allocation_value, 2.0)
        self.assertEqual(copied.allocation_unit, "days")

    def test_subtask_copy_keeps_hierarchy(self):
        parent = self._new_task(name="Parent")
        child = self.env["project.task"].create(
            {
                "name": "Child",
                "project_id": self.project.id,
                "parent_id": parent.id,
                "user_ids": [Command.set([self.task_user.id])],
                "approval_required": True,
            }
        )
        self._add_route(child, [self.approver_1])
        copied_parent = parent.copy()
        self.assertEqual(len(copied_parent.child_ids), 1)
        self.assertEqual(copied_parent.child_ids.parent_id, copied_parent)
        self.assertEqual(copied_parent.child_ids.approval_state, "draft")
