import unittest

from backend.modules.orchestration.langgraph_runner import _normalize_run_mode


class LangGraphRunnerTests(unittest.TestCase):
    def test_normalize_run_mode_accepts_known_modes(self) -> None:
        for mode in ("brainstorm", "review", "debate", "manager_worker", "single_agent"):
            self.assertEqual(_normalize_run_mode(mode), mode)

    def test_normalize_run_mode_unknown_falls_back(self) -> None:
        self.assertEqual(_normalize_run_mode("custom"), "single_agent")
        self.assertEqual(_normalize_run_mode(None), "single_agent")
