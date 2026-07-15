import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class WorkflowConfigurationTests(unittest.TestCase):
    def test_workflow_runs_tests_before_synchronization(self):
        workflow = (
            PROJECT_ROOT / ".github" / "workflows" / "sync-stars.yml"
        ).read_text(encoding="utf-8")

        test_command = "python3 -m unittest discover -s tests -v"
        sync_command = 'python3 scripts/sync_stars.py --username "$STAR_OWNER"'
        self.assertIn(test_command, workflow)
        self.assertIn(sync_command, workflow)
        self.assertLess(workflow.index(test_command), workflow.index(sync_command))
        self.assertIn('"tests/**"', workflow)


if __name__ == "__main__":
    unittest.main()
