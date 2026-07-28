from odoo.exceptions import UserError

from .common import ApprovalMatrixCase


class TestTaskCompletion(ApprovalMatrixCase):
    def test_stage_and_state_completion_are_blocked(self):
        task = self._new_task()
        self._add_route(task)
        for values in (
            {"stage_id": self.closing_stage.id},
            {"state": "1_done"},
        ):
            with self.assertRaisesRegex(
                UserError, "cannot be completed until all required approvals"
            ):
                task.write(values)

    def test_kanban_rpc_and_approved_completion(self):
        task = self._new_task()
        self._add_route(task, [self.approver_1])
        with self.assertRaises(UserError):
            task.write({"stage_id": self.closing_stage.id})
        task.action_submit_for_approval()
        task.with_user(self.approver_1).action_approve()
        task.write({"stage_id": self.closing_stage.id})
        self.assertEqual(task.stage_id, self.closing_stage)

    def test_project_can_opt_out_of_completion_block(self):
        self.project.prevent_task_completion_without_approval = False
        task = self._new_task()
        self._add_route(task)
        task.write({"stage_id": self.closing_stage.id})
        self.assertEqual(task.stage_id, self.closing_stage)
