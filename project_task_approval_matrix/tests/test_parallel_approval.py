from .common import ApprovalMatrixCase


class TestParallelApproval(ApprovalMatrixCase):
    def test_parallel_all_steps_and_partial_state(self):
        task = self._new_task("parallel")
        lines = self._add_route(
            task, [self.approver_1, self.approver_2, self.approver_3]
        )
        task.action_submit_for_approval()
        self.assertEqual(set(lines.mapped("state")), {"pending"})
        self.assertEqual(len(self._linked_activities(task)), 3)

        task.with_user(self.approver_1).action_approve()
        self.assertEqual(task.approval_state, "partially_approved")
        self.assertAlmostEqual(task.approval_progress, 100.0 / 3.0)

        task.with_user(self.approver_2).action_approve()
        self.assertEqual(task.approval_state, "partially_approved")
        task.with_user(self.approver_3).action_approve()
        self.assertEqual(task.approval_state, "approved")
        self.assertFalse(self._linked_activities(task))

    def test_parallel_rejection_cancels_other_steps(self):
        task = self._new_task("parallel")
        lines = self._add_route(
            task, [self.approver_1, self.approver_2, self.approver_3]
        )
        task.action_submit_for_approval()
        lines[1].with_user(self.approver_2).write({"comments": "Cost is too high."})
        task.with_user(self.approver_2).action_reject()
        self.assertEqual(task.approval_state, "rejected")
        self.assertEqual(lines[1].state, "rejected")
        self.assertEqual(set((lines - lines[1]).mapped("state")), {"cancelled"})
        self.assertFalse(self._linked_activities(task))
