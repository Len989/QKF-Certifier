"""Unexpected planner failures preserve charged evidence without a retry."""
import unittest
from unittest.mock import patch

from check27 import audit_episode
from run27 import episode
from scenarios27 import sha


PROTOCOL = "a" * 64


def inputs(strategy):
    portfolio = {"id": "retention_test", "split": "transfer", "program_count": 2,
                 "programs": [{"id": f"program_{n}", "kind": "publish",
                               "components": [{"id": f"task_{n}", "initial": f"A{n}",
                                               "validated": f"B{n}", "next_value": f"C{n}"}]}
                              for n in range(2)]}
    spec = {"portfolio_id": portfolio["id"], "portfolio_sha256": sha(portfolio),
            "backend": "alias_live", "strategy": strategy}
    spec["episode_id"] = "ep_" + sha(spec)[:20]
    return spec, portfolio


class RunnerFailureRetentionTests(unittest.TestCase):
    def assert_rejected(self, record, portfolio, strategy):
        checked = audit_episode(record, portfolio, "alias_live", strategy, PROTOCOL)
        self.assertFalse(checked["integrity_pass"])
        self.assertFalse(checked["pass"])

    def test_acquisition_failure_retains_calls_and_never_starts_task(self):
        for strategy, learner in [("ordinary_fork", "learn_fork"),
                                  ("ordinary_full", "learn_full")]:
            with self.subTest(strategy=strategy):
                spec, portfolio = inputs(strategy)
                def failing_learner(service):
                    handle = service.call("create", value="probe_before")["handle"]
                    service.call("write", handle=handle, value="probe_after")
                    raise RuntimeError("injected acquisition failure after two calls")
                with patch("planners27." + learner, side_effect=failing_learner) as injected:
                    record = episode(spec, portfolio, PROTOCOL)
                self.assertEqual(injected.call_count, 1)
                probe, task = record["services"]["probe"], record["services"]["task"]
                self.assertEqual([e["action"] for e in probe["log"]], ["create", "write"])
                self.assertEqual(probe["total_cost"], 4)
                self.assertEqual(record["total_cost"], 4)
                self.assertEqual(list(probe["final_state"]["cells"].values()),
                                 [{"revision": 2, "value": "probe_after"}])
                self.assertEqual(probe["final_state"]["next_revision"], 3)
                self.assertEqual(task["log"], [])
                self.assertEqual(task["total_cost"], 0)
                self.assertEqual(task["final_state"]["handles"], {})
                self.assertEqual(record["executions"], [])
                self.assertEqual(record["execution_error"], {
                    "type": "RuntimeError", "message": "injected acquisition failure after two calls",
                    "program_id": None, "phase": "acquisition"})
                self.assert_rejected(record, portfolio, strategy)

    def test_online_failure_retains_changed_task_state_without_later_programs(self):
        strategy = "ordinary_online"
        spec, portfolio = inputs(strategy)
        def failing_online(service, programs):
            self.assertEqual(programs, portfolio["programs"])
            task = programs[0]["components"][0]
            handle = service.call("create", value=task["initial"])["handle"]
            service.call("write", handle=handle, value=task["validated"])
            raise RuntimeError("injected online failure after two calls")
        with patch("online27.execute_online_portfolio", side_effect=failing_online) as injected:
            record = episode(spec, portfolio, PROTOCOL)
        self.assertEqual(injected.call_count, 1)
        self.assertIsNone(record["services"]["probe"])
        task = record["services"]["task"]
        self.assertEqual([e["action"] for e in task["log"]], ["create", "write"])
        self.assertEqual(task["total_cost"], 4)
        self.assertEqual(record["total_cost"], 4)
        self.assertEqual(list(task["final_state"]["cells"].values()),
                         [{"revision": 2, "value": "B0"}])
        self.assertEqual(record["executions"], [])
        self.assertEqual(record["execution_error"], {
            "type": "RuntimeError", "message": "injected online failure after two calls",
            "program_id": None, "phase": "online"})
        self.assertEqual(record["knowledge"], {"fork_mode": "unknown", "activation_mode": "unknown",
                                               "source": "charged_task_observations"})
        self.assert_rejected(record, portfolio, strategy)

    def test_charged_live_error_survives_an_unexpected_online_exception(self):
        spec, portfolio = inputs("ordinary_online")
        def failing_online(service, programs):
            handle = service.call("create", value="A")["handle"]
            token = service.call("validate", handle=handle)["token"]
            service.call("write", handle=handle, value="C")
            result = service.call("activate", handle=handle, token=token)
            self.assertEqual(result, {"ok": False, "error": "token_revision_mismatch"})
            raise RuntimeError("injected failure after charged activation error")
        with patch("online27.execute_online_portfolio", side_effect=failing_online) as injected:
            record = episode(spec, portfolio, PROTOCOL)
        self.assertEqual(injected.call_count, 1)
        task = record["services"]["task"]
        self.assertEqual([e["action"] for e in task["log"]], ["create", "validate", "write", "activate"])
        self.assertEqual(record["total_cost"], 9)
        self.assertEqual(task["total_cost"], 9)
        self.assertEqual(task["log"][-1]["cost"], 2)
        self.assertEqual(task["log"][-1]["before_sha256"], task["log"][-1]["after_sha256"])
        self.assertIsNone(task["final_state"]["live"])
        self.assertEqual(list(task["final_state"]["tokens"].values())[0]["value"], "A")
        self.assertEqual(list(task["final_state"]["cells"].values())[0]["value"], "C")
        self.assertEqual(record["execution_error"]["phase"], "online")
        self.assert_rejected(record, portfolio, "ordinary_online")


if __name__ == "__main__":
    unittest.main()
