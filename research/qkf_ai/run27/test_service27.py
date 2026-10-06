"""Contract tests: version preservation, hidden effects and error atomicity."""

import unittest

from service27 import ArtifactService, BACKENDS, COSTS, state_sha256


class ArtifactServiceTests(unittest.TestCase):
    def test_fork_class_effect_and_snapshot_independence(self):
        for backend in BACKENDS:
            with self.subTest(backend=backend):
                service = ArtifactService(backend, seed="fork")
                original = service.call("create", value="A")
                branch = service.call("fork", handle=original["handle"])
                safe = service.call("snapshot", handle=original["handle"])
                changed = service.call("write", handle=branch["handle"], value="B")
                origin_after = service.call("read", handle=original["handle"])
                safe_after = service.call("read", handle=safe["handle"])
                if backend.startswith("copy_"):
                    self.assertEqual((origin_after["revision"], origin_after["value"]),
                                     (original["revision"], "A"))
                else:
                    self.assertEqual((origin_after["revision"], origin_after["value"]),
                                     (changed["revision"], "B"))
                self.assertEqual((safe_after["revision"], safe_after["value"]),
                                 (original["revision"], "A"))

    def test_pin_reuses_immutable_token_live_rejects_changed_revision(self):
        for backend in BACKENDS:
            with self.subTest(backend=backend):
                service = ArtifactService(backend)
                artifact = service.call("create", value="B")
                token = service.call("validate", handle=artifact["handle"])
                service.call("write", handle=artifact["handle"], value="C")
                before_activate = service.export_state()
                activation = service.call("activate", handle=artifact["handle"],
                                          token=token["token"])
                if backend.endswith("_pin"):
                    self.assertEqual(activation,
                                     {"ok": True, "published_revision": artifact["revision"],
                                      "published_value": "B"})
                    self.assertEqual(service.export_state()["live"]["value"], "B")
                else:
                    self.assertEqual(activation,
                                     {"ok": False, "error": "token_revision_mismatch"})
                    self.assertEqual(service.export_state(), before_activate)
                self.assertEqual(service.export_state()["validated_revisions"],
                                 [artifact["revision"]])

    def test_token_cross_handle_reuse_same_exact_revision(self):
        for backend in BACKENDS:
            with self.subTest(backend=backend):
                service = ArtifactService(backend)
                artifact = service.call("create", value="B")
                token = service.call("validate", handle=artifact["handle"])
                preserved = service.call("snapshot", handle=artifact["handle"])
                service.call("write", handle=artifact["handle"], value="C")
                result = service.call("activate", handle=preserved["handle"],
                                      token=token["token"])
                self.assertEqual(result,
                                 {"ok": True, "published_revision": artifact["revision"],
                                  "published_value": "B"})

    def test_equal_content_does_not_make_revision_equal(self):
        service = ArtifactService("copy_live")
        first = service.call("create", value="B")
        token = service.call("validate", handle=first["handle"])
        recreated = service.call("create", value="B")
        self.assertNotEqual(first["revision"], recreated["revision"])
        before = service.export_state()
        self.assertEqual(service.call("activate", handle=recreated["handle"],
                                      token=token["token"]),
                         {"ok": False, "error": "token_revision_mismatch"})
        self.assertEqual(service.export_state(), before)

    def test_live_snapshot_remains_fixed_after_later_writes(self):
        service = ArtifactService("alias_live")
        artifact = service.call("create", value="B")
        token = service.call("validate", handle=artifact["handle"])
        service.call("activate", handle=artifact["handle"], token=token["token"])
        live_before = service.export_state()["live"]
        service.call("write", handle=artifact["handle"], value="C")
        self.assertEqual(service.export_state()["live"], live_before)

    def test_strict_errors_are_charged_and_do_not_change_domain_state(self):
        service = ArtifactService("copy_pin")
        artifact = service.call("create", value="A")
        malformed = [
            ("write", {"handle": artifact["handle"], "value": 123}, "invalid_arguments"),
            ("write", {"handle": artifact["handle"], "value": True}, "invalid_arguments"),
            ("read", {"handle": artifact["handle"], "extra": "x"}, "invalid_arguments"),
            ("write", {"handle": "missing", "value": "B"}, "unknown_handle"),
            ("activate", {"handle": artifact["handle"], "token": "missing"}, "unknown_token"),
            ("delete", {"handle": artifact["handle"]}, "unknown_operation"),
        ]
        total = 2
        for action, args, error in malformed:
            with self.subTest(action=action, args=args):
                before = service.export_state()
                self.assertEqual(service.call(action, **args), {"ok": False, "error": error})
                self.assertEqual(service.export_state(), before)
                total += COSTS.get(action, 1)
                self.assertEqual(service.total_cost, total)
                entry = service.export_log()[-1]
                self.assertEqual(entry["before_sha256"], entry["after_sha256"])
                self.assertEqual(entry["after_sha256"], state_sha256(before))

    def test_identifiers_do_not_leak_backend_and_exports_are_detached(self):
        ids = []
        for backend in BACKENDS:
            service = ArtifactService(backend, seed="paired")
            artifact = service.call("create", value="A")
            token = service.call("validate", handle=artifact["handle"])
            branch = service.call("fork", handle=artifact["handle"])
            ids.append((artifact["handle"], token["token"], branch["handle"]))
            state = service.export_state()
            state["cells"].clear()
            log = service.export_log()
            log[0]["result"]["handle"] = "forged"
            self.assertTrue(service.export_state()["cells"])
            self.assertNotEqual(service.export_log()[0]["result"]["handle"], "forged")
        self.assertEqual(len(set(ids)), 1)

    def test_safe_multistep_plan_preserves_A_deploys_B_keeps_C_workspace(self):
        for backend in BACKENDS:
            with self.subTest(backend=backend):
                service = ArtifactService(backend)
                source = service.call("create", value="A")
                preserved_A = service.call("snapshot", handle=source["handle"])
                changed_B = service.call("write", handle=source["handle"], value="B")
                token_B = service.call("validate", handle=source["handle"])
                preserved_B = service.call("snapshot", handle=source["handle"])
                changed_C = service.call("write", handle=source["handle"], value="C")
                activated = service.call("activate", handle=preserved_B["handle"],
                                         token=token_B["token"])
                A = service.call("read", handle=preserved_A["handle"])
                C = service.call("read", handle=source["handle"])
                self.assertEqual((A["revision"], A["value"]), (source["revision"], "A"))
                self.assertEqual((activated["published_revision"], activated["published_value"]),
                                 (changed_B["revision"], "B"))
                self.assertEqual((C["revision"], C["value"]), (changed_C["revision"], "C"))
                self.assertEqual(service.total_cost, 19)


if __name__ == "__main__":
    unittest.main()
