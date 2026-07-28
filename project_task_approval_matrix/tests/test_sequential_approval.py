from odoo.exceptions import AccessError, UserError, ValidationError

from .common import ApprovalMatrixCase


class TestSequentialApproval(ApprovalMatrixCase):
    def test_disabled_project_behaves_normally(self):
        project = self.env["project.project"].create(
            {"name": "Standard Project", "approval_matrix_enabled": False}
        )
        task = self.env["project.task"].create(
            {"name": "Standard Task", "project_id": project.id}
        )
        self.assertFalse(task.project_approval_enabled)
        self.assertEqual(task.approval_state, "not_required")
        with self.assertRaises(ValidationError):
            task.write({"approval_required": True})
        with self.assertRaises(UserError):
            task.action_submit_for_approval()

    def test_sequential_activates_one_step_at_a_time(self):
        task = self._new_task()
        lines = self._add_route(task)
        task.action_submit_for_approval()
        self.assertEqual(lines.mapped("state"), ["pending", "waiting"])
        self.assertEqual(len(self._linked_activities(task)), 1)

        with self.assertRaises(AccessError):
            task.with_user(self.approver_2).action_approve()

        task.with_user(self.approver_1).action_approve()
        self.assertEqual(lines.mapped("state"), ["approved", "pending"])
        self.assertEqual(task.approval_state, "submitted")
        self.assertEqual(self._linked_activities(task).user_id, self.approver_2)

        task.with_user(self.approver_2).action_approve()
        self.assertEqual(lines.mapped("state"), ["approved", "approved"])
        self.assertEqual(task.approval_state, "approved")
        self.assertEqual(task.approval_progress, 100.0)
        self.assertTrue(task.approved_date)
        self.assertFalse(self._linked_activities(task))

    def test_request_changes_requires_comments_and_resubmits(self):
        task = self._new_task()
        lines = self._add_route(task)
        task.action_submit_for_approval()
        with self.assertRaises(ValidationError):
            task.with_user(self.approver_1).action_request_changes()
        lines[0].with_user(self.approver_1).write({"comments": "Revise the sample."})
        task.with_user(self.approver_1).action_request_changes()
        self.assertEqual(task.approval_state, "changes_requested")
        self.assertFalse(self._linked_activities(task))

        task.action_submit_for_approval()
        self.assertEqual(task.approval_state, "submitted")
        self.assertEqual(lines.mapped("state"), ["pending", "waiting"])
        self.assertFalse(any(lines.mapped("comments")))

    def test_rejection_closes_round(self):
        task = self._new_task()
        lines = self._add_route(task)
        task.action_submit_for_approval()
        lines[0].with_user(self.approver_1).write({"comments": "Not compliant."})
        task.with_user(self.approver_1).action_reject()
        self.assertEqual(task.approval_state, "rejected")
        self.assertEqual(lines.mapped("state"), ["rejected", "cancelled"])
        self.assertFalse(self._linked_activities(task))

    def test_normal_task_and_subtask_need_no_approval(self):
        task = self.env["project.task"].create(
            {
                "name": "No Approval",
                "project_id": self.project.id,
                "stage_id": self.open_stage.id,
            }
        )
        subtask = self.env["project.task"].create(
            {
                "name": "No Approval Subtask",
                "project_id": self.project.id,
                "parent_id": task.id,
                "stage_id": self.open_stage.id,
            }
        )
        task.write({"stage_id": self.closing_stage.id})
        subtask.write({"stage_id": self.closing_stage.id})
        self.assertEqual(task.stage_id, self.closing_stage)
        self.assertEqual(subtask.stage_id, self.closing_stage)
