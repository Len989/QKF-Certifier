"""Meaningful planner-contract tests against the actual independently written API."""

import unittest

from planners27 import (Knowledge, PlannerFailure, execute_program, execute_task, learn_fork,
                        learn_full, select_budgeted_policy, expected_portfolio_costs)
from service27 import ArtifactService


class CallOnly:
    """Expose the request callback and fail accidental harness/state access."""

    def __init__(self, service):
        object.__setattr__(self, "call", service.call)

    def __getattr__(self, name):
        raise AssertionError(f"planner attempted forbidden service attribute: {name}")


def case(index=0):
    return {"id": f"public-task-{index}", "initial": f"A:{index}",
            "validated": f"B:{index}", "next_value": f"C:{index}"}


def oracle(backend):
    fork, activate = backend.split("_")
    return Knowledge(fork, "pinned" if activate == "pin" else "live")


def value_at(state, handle):
    return state["cells"][state["handles"][handle]]["value"]


def assert_goal(test, service, task, result):
    state = service.export_state()
    test.assertEqual(value_at(state, result["handles"]["source"]), task["next_value"])
    test.assertEqual(value_at(state, result["handles"]["backup"]), task["initial"])
    test.assertEqual(state["live"]["value"], task["validated"])
    test.assertIn(state["live"]["revision"], state["validated_revisions"])


class PlannerTests(unittest.TestCase):
    backends = ("copy_pin", "copy_live", "alias_pin", "alias_live")

    def test_safe_and_oracle_preserve_all_goals_and_registered_costs(self):
        expected = {"copy_pin": 12, "copy_live": 13,
                    "alias_pin": 14, "alias_live": 17}
        for backend in self.backends:
            for knowledge, cost in ((None, 17), (oracle(backend), expected[backend])):
                with self.subTest(backend=backend, knowledge=knowledge):
                    service = ArtifactService(backend, seed="same-visible-seed")
                    task = case()
                    result = execute_task(CallOnly(service), task, knowledge)
                    assert_goal(self, service, task, result)
                    self.assertEqual(service.total_cost, cost)

    def test_full_learning_uses_only_calls_and_charges_failed_activation(self):
        for backend in self.backends:
            with self.subTest(backend=backend):
                service = ArtifactService(backend, seed="same-probe-seed")
                knowledge, trace = learn_full(CallOnly(service))
                self.assertEqual(knowledge, oracle(backend))
                self.assertEqual(service.total_cost, 11)
                self.assertEqual([entry["action"] for entry in trace],
                                 ["create", "fork", "validate", "write", "read", "activate"])
                if backend.endswith("live"):
                    self.assertEqual(trace[-1]["result"],
                                     {"ok": False, "error": "token_revision_mismatch"})
                    self.assertIsNone(service.export_state()["live"])
                # Knowledge transfers to a fresh state containing no probe artifact.
                production = ArtifactService(backend, seed="fresh-production")
                task = case(1)
                result = execute_task(CallOnly(production), task, knowledge)
                assert_goal(self, production, task, result)

    def test_fork_only_learning_preserves_unknown_activation_and_full_cost(self):
        for backend in self.backends:
            with self.subTest(backend=backend):
                probe = ArtifactService(backend)
                knowledge, _ = learn_fork(CallOnly(probe))
                self.assertEqual(knowledge.fork_mode, oracle(backend).fork_mode)
                self.assertEqual(knowledge.activation_mode, "unknown")
                self.assertEqual(probe.total_cost, 6)
                production = ArtifactService(backend)
                task = case()
                result = execute_task(CallOnly(production), task, knowledge)
                assert_goal(self, production, task, result)
                self.assertEqual(production.total_cost,
                                 13 if backend.startswith("copy") else 17)

    def test_wrong_fork_knowledge_really_destroys_required_backup(self):
        service = ArtifactService("alias_pin")
        task = case()
        result = execute_task(CallOnly(service), task, Knowledge("copy", "pinned"))
        state = service.export_state()
        self.assertEqual(state["live"]["value"], task["validated"])
        self.assertEqual(value_at(state, result["handles"]["backup"]), task["next_value"])
        self.assertNotEqual(value_at(state, result["handles"]["backup"]), task["initial"])

    def test_wrong_activation_knowledge_is_rejected_after_source_advance(self):
        service = ArtifactService("copy_live")
        program = {"id": "p-failing", "kind": "publish", "components": [case()]}
        with self.assertRaises(PlannerFailure) as caught:
            execute_program(CallOnly(service), program, Knowledge("copy", "pinned"))
        self.assertEqual(service.export_log()[-1]["result"],
                         {"ok": False, "error": "token_revision_mismatch"})
        self.assertIsNone(service.export_state()["live"])
        self.assertEqual(service.export_log()[-2]["args"]["value"], "C:0")
        partial = caught.exception.partial_program
        self.assertEqual(partial["id"], program["id"])
        self.assertEqual(len(partial["components"]), 1)
        trace = partial["components"][0]["trace"]
        self.assertEqual(trace[-1]["phase"], "publish")
        self.assertEqual(trace[-1]["result"], service.export_log()[-1]["result"])

    def test_portfolio_budget_never_inspects_true_backend(self):
        self.assertEqual([select_budgeted_policy(count) for count in (1, 4, 6, 12, 18, 32)],
                         ["safe", "online", "online", "online", "online", "online"])
        self.assertEqual(expected_portfolio_costs(1),
                         {"safe": 17, "fork": 21, "full": 25, "online": 19})
        self.assertEqual(expected_portfolio_costs(4),
                         {"safe": 68, "fork": 66, "full": 67, "online": 61})
        for invalid in (True, 0, -1, 1.5):
            with self.assertRaises(ValueError):
                select_budgeted_policy(invalid)

    def test_composed_rollback_and_pair_transfer_preserves_old_handles(self):
        for backend in self.backends:
            with self.subTest(backend=backend):
                service = ArtifactService(backend, seed="composed")
                knowledge = oracle(backend)
                rollback = {"id": "p-r", "kind": "rollback", "components": [case(1)]}
                first = execute_program(CallOnly(service), rollback, knowledge)
                old_handles = first["components"][0]["handles"]
                self.assertEqual(service.export_state()["live"]["value"], "A:1")
                pair = {"id": "p-p", "kind": "paired_publish",
                        "components": [case(2), case(3)]}
                result = execute_program(CallOnly(service), pair, knowledge)
                state = service.export_state()
                self.assertEqual(state["live"]["value"], "B:3")
                self.assertEqual(value_at(state, old_handles["backup"]), "A:1")
                self.assertEqual(value_at(state, old_handles["source"]), "C:1")
                for component, task in zip(result["components"], pair["components"]):
                    self.assertEqual(value_at(state, component["handles"]["backup"]), task["initial"])
                    self.assertEqual(value_at(state, component["handles"]["source"]), task["next_value"])
                activations = [entry["result"]["published_value"]
                               for entry in service.export_log()
                               if entry["action"] == "activate" and entry["result"]["ok"]]
                self.assertEqual(activations, ["B:1", "A:1", "B:2", "B:3"])

    def test_learner_rejects_unregistered_public_outcomes(self):
        service = ArtifactService("copy_pin")

        class StrangeRead:
            def call(self, action, **kwargs):
                result = service.call(action, **kwargs)
                return {"ok": True, "value": "unexpected", "revision": 1} if action == "read" else result

        with self.assertRaises(RuntimeError):
            learn_full(StrangeRead())


if __name__ == "__main__":
    unittest.main()
