from .common import ApprovalMatrixCase


class TestProjectDuplication(ApprovalMatrixCase):
    def test_project_copy_uses_standard_task_mapping_once(self):
        parent = self._new_task(name="Parent Copy Test")
        self._add_route(parent)
        child = self._new_task(name="Child Copy Test", parent_id=parent.id)
        self._add_route(child, [self.approver_3])

        copied_project = self.project.copy({"name": "Copied Approval Project"})
        copied_tasks = self.env["project.task"].search(
            [("project_id", "=", copied_project.id)]
        )
        self.assertEqual(len(copied_tasks), 2)
        copied_parent = copied_tasks.filtered(lambda task: not task.parent_id)
        copied_child = copied_tasks.filtered("parent_id")
        self.assertEqual(copied_child.parent_id, copied_parent)
        self.assertTrue(copied_project.approval_matrix_enabled)
        self.assertTrue(
            copied_project.prevent_task_completion_without_approval
        )
        self.assertEqual(copied_parent.approval_state, "draft")
        self.assertEqual(copied_child.approval_state, "draft")
        self.assertEqual(len(copied_parent.approval_line_ids), 2)
        self.assertEqual(len(copied_child.approval_line_ids), 1)
