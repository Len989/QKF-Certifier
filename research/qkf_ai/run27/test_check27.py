"""Cross-implementation integrity guards, using the harness only as producer.

The checker imports no producer modules. Tests deliberately corrupt valid raw
records and verify that intact wrong-fact experiments fail goals separately.
"""
import copy
import hashlib
import json
import unittest

from check27 import audit_episode
from run27 import episode


PROTOCOL = "a" * 64


def digest(value):
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def fixture(backend="copy_pin", strategy="safe", kind="publish", count=1):
    programs = []
    for index in range(count):
        components = [{"id": f"p{index}_unit{n}", "initial": f"A{index}:{n}",
                       "validated": f"B{index}:{n}", "next_value": f"C{index}:{n}"}
                      for n in range(2 if kind == "paired_publish" else 1)]
        programs.append({"id": f"program{index}", "kind": kind, "components": components})
    portfolio = {"id": "fixture", "split": "transfer", "program_count": count,
                 "programs": programs}
    spec = {"portfolio_id": portfolio["id"], "portfolio_sha256": digest(portfolio),
            "backend": backend, "strategy": strategy}
    spec["episode_id"] = "ep_" + digest(spec)[:20]
    return episode(spec, portfolio, PROTOCOL), portfolio


def audit(record, portfolio, backend="copy_pin", strategy="safe"):
    return audit_episode(record, portfolio, backend, strategy, PROTOCOL)


class IndependentCheckerTests(unittest.TestCase):
    def test_correct_backends_and_unprobed_compositions(self):
        for backend in ("copy_pin", "copy_live", "alias_pin", "alias_live"):
            for kind in ("publish", "rollback", "paired_publish"):
                for strategy in ("safe", "oracle", "ordinary_fork", "ordinary_full", "ordinary_best", "ordinary_online"):
                    with self.subTest(backend=backend, kind=kind, strategy=strategy):
                        record, portfolio = fixture(backend, strategy, kind)
                        result = audit(record, portfolio, backend, strategy)
                        self.assertTrue(result["pass"], result)

    def test_result_type_forgery_rejected_even_when_truthy(self):
        record, portfolio = fixture()
        record["services"]["task"]["log"][0]["result"]["ok"] = 1
        self.assertFalse(audit(record, portfolio)["integrity_pass"])

    def test_whole_terminal_state_and_counters_checked(self):
        record, portfolio = fixture()
        record["services"]["task"]["final_state"]["next_revision"] += 1
        self.assertFalse(audit(record, portfolio)["integrity_pass"])

    def test_charges_and_probe_omission_rejected(self):
        record, portfolio = fixture("alias_live", "ordinary_full")
        record["total_cost"] -= record["services"]["probe"]["total_cost"]
        self.assertFalse(audit(record, portfolio, "alias_live", "ordinary_full")["integrity_pass"])
        record, portfolio = fixture("alias_live", "ordinary_full")
        record["services"]["probe"] = None
        self.assertFalse(audit(record, portfolio, "alias_live", "ordinary_full")["integrity_pass"])

    def test_backend_protocol_input_and_scope_binding(self):
        record, portfolio = fixture()
        mutations = [("backend", "alias_live"), ("protocol_sha", "b" * 64),
                     ("portfolio_sha256", "b" * 64),
                     ("interface_scope", {"model": "other", "portfolio_id": "fixture"})]
        for key, value in mutations:
            forged = copy.deepcopy(record)
            forged[key] = value
            self.assertFalse(audit(forged, portfolio)["integrity_pass"], key)

    def test_truth_relabelled_as_earned_knowledge_rejected(self):
        record, portfolio = fixture("copy_pin", "ordinary_fork")
        record["knowledge"]["activation_mode"] = "pinned"
        self.assertFalse(audit(record, portfolio, "copy_pin", "ordinary_fork")["integrity_pass"])

    def test_planner_call_omission_rejected(self):
        record, portfolio = fixture()
        record["executions"][0]["components"][0]["trace"].pop(2)
        self.assertFalse(audit(record, portfolio)["integrity_pass"])

    def test_wrong_facts_are_valid_experiments_with_failed_goals(self):
        for backend, strategy in [("alias_pin", "oracle_wrong_fork"),
                                  ("alias_live", "oracle_wrong_fork"),
                                  ("copy_live", "oracle_wrong_activation")]:
            record, portfolio = fixture(backend, strategy)
            result = audit(record, portfolio, backend, strategy)
            self.assertTrue(result["integrity_pass"], result)
            self.assertFalse(result["goal_pass"], result)

    def test_plan_and_reported_roles_cannot_contradict_recorded_knowledge(self):
        record, portfolio = fixture()
        record["executions"][0]["components"][0]["knowledge"]["fork_mode"] = "copy"
        self.assertFalse(audit(record, portfolio)["integrity_pass"])
        record, portfolio = fixture()
        record["executions"][0]["components"][0]["handles"]["backup"] = "invented"
        self.assertFalse(audit(record, portfolio)["integrity_pass"])

    def test_online_observations_are_charged_and_knowledge_is_earned(self):
        for backend in ("copy_pin", "copy_live", "alias_pin", "alias_live"):
            record, portfolio = fixture(backend, "ordinary_online", count=4)
            result = audit(record, portfolio, backend, "ordinary_online")
            self.assertTrue(result["pass"], result)
            self.assertEqual(result["probe_cost"], 0)
            # A forged learned fact cannot be accepted because the real task's
            # read/activation outcomes, including charged LIVE failure, govern it.
            forged = copy.deepcopy(record)
            fact = forged["executions"][0]["components"][0]["learned_knowledge"]
            fact["fork_mode"] = "alias" if fact["fork_mode"] == "copy" else "copy"
            self.assertFalse(audit(forged, portfolio, backend, "ordinary_online")["integrity_pass"])
            forged = copy.deepcopy(record)
            forged["executions"][0]["components"][0]["knowledge"]["fork_mode"] = "copy"
            self.assertFalse(audit(forged, portfolio, backend, "ordinary_online")["integrity_pass"])
            forged = copy.deepcopy(record)
            forged["services"]["task"]["log"][8]["cost"] = 0
            self.assertFalse(audit(forged, portfolio, backend, "ordinary_online")["integrity_pass"])
            forged = copy.deepcopy(record)
            forged["executions"][1]["components"][0]["knowledge"]["activation_mode"] = "unknown"
            self.assertFalse(audit(forged, portfolio, backend, "ordinary_online")["integrity_pass"])

    def test_online_observation_omission_rejected(self):
        record, portfolio = fixture("copy_live", "ordinary_online")
        record["executions"][0]["components"][0]["trace"].pop(4)
        self.assertFalse(audit(record, portfolio, "copy_live", "ordinary_online")["integrity_pass"])

    def test_error_cannot_hide_missing_calls(self):
        record, portfolio = fixture("copy_live", "oracle_wrong_activation")
        self.assertTrue(audit(record, portfolio, "copy_live", "oracle_wrong_activation")["integrity_pass"])
        record["services"]["task"]["log"].pop()
        self.assertFalse(audit(record, portfolio, "copy_live", "oracle_wrong_activation")["integrity_pass"])


if __name__ == "__main__":
    unittest.main()
