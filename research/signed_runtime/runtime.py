"""Load a PR29 proof once; execute its immutable row action many times.

The loader checks the complete source-bound proof, including native atom labels
and completion. No raw runtime-JSON restore is provided. Core constructors alone
are structural validators, not a way to certify an unrelated source program.
The Python process and implementation remain trusted (not a security sandbox).
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json

from research.signed_observations.checker import rebuild
from research.signed_bridge.model import COMPLETION, EMPTY
from .core import AtomicRow, Machine, integer, require

ENGINE = "signed-atomic-row-runtime-v1"
MAX_WORD_BITS = 4096
MAX_STREAM_BITS = 1_048_576


class ExecutionLimit(ValueError):
    """An execution resource ceiling, not a counterexample or proof failure."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Runner:
    """An immutable execution view. Only load() establishes its source binding."""
    machine: Machine
    # Immutable scalar identity, deliberately not a reference to the proof/source.
    identity: tuple[tuple[str, str], ...]

    def __post_init__(self):
        require(type(self.machine) is Machine and self.machine.alphabet == ("0", "1")
                and self.machine.outputs == ("_",), "signed binary runtime profile")
        require(type(self.identity) is tuple
                and all(type(p) is tuple and len(p) == 2
                        and all(type(x) is str for x in p) for p in self.identity),
                "immutable runtime identity")
        m = self.machine
        require(m.terminal[m.initial] == EMPTY
                and all(label in {"true", "false"} for i, label in enumerate(m.terminal)
                        if i != m.initial), "positive-width completion labels")
        require(all(m.step(i, a)[1] != m.initial for i in range(m.classes) for a in m.alphabet),
                "no nonempty trace may return to empty initialization")

    def start(self):
        return _Cursor(self, self.machine.initial, 0)

    def run(self, symbols, *, max_bits=MAX_STREAM_BITS):
        """Consume LSB-first symbols, storing only a class and a bit count."""
        return self.start().feed(symbols, max_bits=max_bits)

    def value(self, raw, width):
        """Finite raw two's-complement word, explicitly NOT implicit modulo input."""
        require(integer(width, 1, MAX_WORD_BITS), "word width must be 1..4096")
        require(integer(raw, 0, (1 << width) - 1), "raw word outside its width")
        return self.run((str((raw >> i) & 1) for i in range(width))).finish()

    def describe(self):
        view = self.machine.snapshot()
        return {"schema": "qkf-signed-row-runtime-view-v1", "engine": ENGINE,
                "kind": "inspection-only-not-a-certificate", "identity": dict(self.identity),
                "action": view, "action_sha256": digest(view),
                "completion": COMPLETION, "target_checked": False, "lean_checked": False}


@dataclass(frozen=True, slots=True)
class _Cursor:
    runner: Runner
    state: int
    width: int

    def feed(self, symbols, *, max_bits=MAX_STREAM_BITS):
        require(integer(max_bits, 0, MAX_STREAM_BITS), "stream budget must be 0..1048576")
        if self.width > max_bits:
            raise ExecutionLimit("existing prefix exceeds stream budget")
        state, width = self.state, self.width
        for symbol in symbols:
            if width >= max_bits:
                raise ExecutionLimit("stream bit budget exhausted")
            _, state = self.runner.machine.step(state, symbol)
            width += 1
        # Immutable: failure never changes this cursor or leaves a partial result.
        return _Cursor(self.runner, state, width)

    @property
    def terminal(self):
        return self.runner.machine.terminal[self.state]

    def finish(self):
        require(self.width > 0 and self.terminal in {"true", "false"},
                "empty input is not a positive-width word")
        return self.terminal == "true"


def load(source, selection, certificate):
    """Return (Runner, receipt) only after full source/observation validation.

Snapshot caller-owned dictionaries before validation. No mutable proof/model,
source, residual interpreter, or forward cell table survives in the Runner.
Concurrent caller mutation during snapshot and hostile Python reflection are
outside this ordinary in-process API contract.
"""
    selection, certificate = deepcopy(selection), deepcopy(certificate)
    ir, model, observation = rebuild(source, selection, certificate)
    proof = certificate["observations"]
    blocks = proof["blocks"]
    require(blocks[proof["initial"]] == [model.initial]
            and model.terminal[model.initial] == EMPTY, "protected initialization class")
    # All rows, including their empty-cell derivations, have already been checked
    # against source-native singleton preimages by the unchanged PR29 chain.
    indexed = {(r["symbol"], r["output"]): r for r in proof["rows"]}
    rows = tuple(tuple(AtomicRow(tuple(dict(indexed[a, y]["supplied"])[1 << j]
                                      for j in range(len(blocks))))
                       for y in model.outputs) for a in model.alphabet)
    machine = Machine(tuple(model.alphabet), tuple(model.outputs),
                      tuple(model.terminal[b[0]] for b in blocks), proof["initial"], rows)
    # The redundant checked forward cells are an audit oracle, never a runtime
    # data source. Enumerate row-recovered actions to detect extraction mistakes.
    recovered = [{"symbol": a, "state": i, "output": machine.step(i, a)[0],
                  "next": machine.step(i, a)[1]}
                 for a in machine.alphabet for i in range(machine.classes)]
    require(recovered == proof["cells"], "row extraction disagrees with checked cells")
    identity = tuple(sorted({"source_sha256": ir["source_sha256"],
                             "request_sha256": digest(selection),
                             "certificate_sha256": digest(certificate),
                             "model_sha256": model.sha256,
                             "contract": selection["contract"],
                             "word_type": selection["word_type"]}.items()))
    runner = Runner(machine, identity)
    receipt = {"schema": "qkf-signed-row-runtime-result-v1", "engine": ENGINE,
               "status": "source_runtime_verified", "claim": "source_row_runtime_equivalence",
               "identity": dict(identity), "action_sha256": digest(machine.snapshot()),
               "classes": machine.classes, "positive_classes": machine.classes - 1,
               "model_states_at_load": len(model.states), "row_templates": len(indexed),
               "stored_atom_images": sum(len(row.atoms) for family in rows for row in family),
               "audited_factor_edges": len(recovered), "forward_cells_retained": 0,
               "residual_states_retained": 0, "powerset_tables_materialized": 0,
               "source_check": "PR28 reconstruction and PR29 atomic observation replay",
               "minimality": observation["minimality"], "completion": COMPLETION,
               "all_positive_widths_in_declared_profile": True,
               "target_checked": False, "lean_checked": False,
               "scope": "source-equivalent row execution under retained restricted semantics; not a target proof"}
    return runner, receipt
