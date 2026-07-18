import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class WorkflowConfigurationTests(unittest.TestCase):
    def test_workflow_runs_tests_before_synchronization(self):
        workflow = (
            PROJECT_ROOT / ".github" / "workflows" / "sync-stars.yml"
        ).read_text(encoding="utf-8")

        test_command = "python -m unittest discover -s tests -v"
        sync_command = 'python scripts/sync_stars.py --username "$STAR_OWNER"'
        self.assertIn(test_command, workflow)
        self.assertIn(sync_command, workflow)
        self.assertLess(workflow.index(test_command), workflow.index(sync_command))
        self.assertIn('"tests/**"', workflow)

    def test_workflow_limits_write_permission_to_sync_job(self):
        workflow = (
            PROJECT_ROOT / ".github" / "workflows" / "sync-stars.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("if: github.event_name != 'push'", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("actions/setup-python@v5", workflow)
        self.assertIn('python-version: "3.12"', workflow)


if __name__ == "__main__":
    unittest.main()
