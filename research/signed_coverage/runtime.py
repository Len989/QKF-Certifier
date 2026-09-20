"""Explicit loading boundary for new covered interfaces, never old-schema spoofing."""
from copy import deepcopy
from research.observations.model import digest, require
from research.signed_runtime.core import AtomicRow, Machine
from research.signed_runtime.runtime import Runner
from research.signed_bridge.model import COMPLETION
from .checker import rebuild_observations
from .local import ENGINE


def load(source, selection, certificate):
    selection, certificate = deepcopy(selection), deepcopy(certificate)
    ir, model, checked, metrics = rebuild_observations(source, selection, certificate)
    proof = certificate["observations"]
    blocks = proof["blocks"]
    indexed = {(r["symbol"], r["output"]): r for r in proof["rows"]}
    rows = tuple(tuple(AtomicRow(tuple(dict(indexed[a, y]["supplied"])[1 << j]
                                      for j in range(len(blocks))))
                       for y in model.outputs) for a in model.alphabet)
    machine = Machine(tuple(model.alphabet), tuple(model.outputs),
                      tuple(model.terminal[b[0]] for b in blocks), proof["initial"], rows)
    recovered = [{"symbol": a, "state": i, "output": machine.step(i, a)[0], "next": machine.step(i, a)[1]}
                 for a in machine.alphabet for i in range(machine.classes)]
    require(recovered == proof["cells"], "checked covered row extraction agrees with cells")
    identity = tuple(sorted({"source_sha256": ir["source_sha256"], "request_sha256": digest(selection),
                             "certificate_sha256": digest(certificate), "model_sha256": model.sha256,
                             "contract": selection["contract"], "word_type": selection["word_type"]}.items()))
    runner = Runner(machine, identity)
    receipt = {"schema": "qkf-signed-guarded-runtime-result-v1", "engine": ENGINE,
               "status": "source_runtime_verified", "claim": "source_guarded_row_equivalence",
               "identity": dict(identity), "action_sha256": digest(machine.snapshot()),
               "classes": machine.classes, "coverage": metrics,
               "source_check": "checked reduction, guarded derivative coverage, atomic observation replay",
               "forward_cells_retained": 0, "residual_states_retained": 0,
               "completion": COMPLETION, "target_checked": False, "lean_checked": False,
               "minimality": checked["minimality"]}
    return runner, receipt
