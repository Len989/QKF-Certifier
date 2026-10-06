"""The stronger baseline earns knowledge safely during charged real work."""
import unittest

from online27 import execute_online_portfolio
from run27 import PublicCalls
from service27 import ArtifactService


def program(identifier, kind="publish"):
    count = 2 if kind == "paired_publish" else 1
    return {"id": identifier, "kind": kind,
            "components": [{"id": f"{identifier}:{i}",
                            "initial": f"{identifier}:{i}:A",
                            "validated": f"{identifier}:{i}:B",
                            "next_value": f"{identifier}:{i}:C"}
                           for i in range(count)]}


class OnlineBaselineTests(unittest.TestCase):
    def test_first_task_cost_and_earned_observations_all_classes(self):
        expected = {"copy_pin": 17, "copy_live": 19,
                    "alias_pin": 19, "alias_live": 21}
        for backend, cost in expected.items():
            with self.subTest(backend=backend):
                service = ArtifactService(backend)
                executions, knowledge = execute_online_portfolio(PublicCalls(service.call), [program("first")])
                self.assertEqual(service.total_cost, cost)
                self.assertEqual(knowledge.fork_mode, backend.split("_")[0])
                self.assertEqual(knowledge.activation_mode, "pinned" if backend.endswith("pin") else "live")
                component = executions[0]["components"][0]
                state = service.export_state()
                for role, value in [("backup", "first:0:A"), ("source", "first:0:C")]:
                    self.assertEqual(state["cells"][state["handles"][component["handles"][role]]]["value"], value)
                self.assertEqual(state["live"]["value"], "first:0:B")
                failures = [e for e in service.export_log() if e["result"]["ok"] is False]
                self.assertEqual(len(failures), int(backend.endswith("live")))
                self.assertTrue(all(e["cost"] == 2 for e in failures))

    def test_facts_reused_in_new_compositions_and_rollback(self):
        first_cost = {"copy_pin": 17, "copy_live": 19, "alias_pin": 19, "alias_live": 21}
        regular = {"copy_pin": 12, "copy_live": 13, "alias_pin": 14, "alias_live": 17}
        for backend in first_cost:
            for first_kind in ["publish", "rollback", "paired_publish"]:
                with self.subTest(backend=backend, first_kind=first_kind):
                    service = ArtifactService(backend)
                    programs = [program("first", first_kind), program("second", "paired_publish"), program("third", "rollback")]
                    executions, knowledge = execute_online_portfolio(PublicCalls(service.call), programs)
                    units = sum(len(p["components"]) for p in programs)
                    overhead = 5 * sum(p["kind"] == "rollback" for p in programs)
                    self.assertEqual(service.total_cost, first_cost[backend] + regular[backend] * (units - 1) + overhead)
                    for execution, planned in zip(executions, programs):
                        for result, task in zip(execution["components"], planned["components"]):
                            state = service.export_state()
                            for role, wanted in [("backup", task["initial"]), ("source", task["next_value"])]:
                                handle = result["handles"][role]
                                self.assertEqual(state["cells"][state["handles"][handle]]["value"], wanted)
                    self.assertEqual(service.export_state()["live"]["value"], "third:0:A")
                    self.assertEqual(sum(part.get("online_learning", False) for ex in executions for part in ex["components"]), 1)


if __name__ == "__main__":
    unittest.main()
