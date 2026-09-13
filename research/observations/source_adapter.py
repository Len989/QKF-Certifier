"""Enumerate the existing native cell, without importing its manual quotient.

Only two reviewed Python function bodies (require/source_cell) are executed.
This is an adapter for trusted repository source, not a sandbox or Java parser.
"""
import ast
import hashlib
from pathlib import Path

from .model import MODEL_SCHEMA, Model, require

PINNED_COMMIT = "d7e631155b9382c787baf72a28b1e335a7074d7e"
PINNED_SOURCE_SHA256 = "ff94f5f1c54f7801c6f26ef412611a0c05b00d78ca48086f0f0b6796bd17f2cf"
PROGRAM = {"mandatory_action": "or", "forbidden_action": "add", "first_action": "add"}


def native_model(source, program=None):
    program = dict(PROGRAM if program is None else program)
    tree = ast.parse(source)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in {"require", "source_cell"}]
    require(len(functions) == 2 and {n.name for n in functions} == {"require", "source_cell"},
            "exact native function definitions")
    namespace = {}
    exec(compile(ast.Module(body=functions, type_ignores=[]), "native_cell", "exec"), namespace)
    cell = namespace["source_cell"]
    columns = [(m, a, g) for m in (0, 1) for a in (0, 1) for g in (0, 1) if m <= g <= a]
    phase0 = (False, 0)
    phases, pending, rows = {phase0}, [phase0], []

    def name(p):
        return f"incremented={int(p[0])},carry={p[1]}"

    for phase in pending:
        for m, a, g in columns:
            y, next_phase = cell(program, phase, m, a, g)
            require(type(y) is int and y in (0, 1) and type(next_phase) is tuple
                    and len(next_phase) == 2 and type(next_phase[0]) is bool
                    and type(next_phase[1]) is int and next_phase[1] in (0, 1), "native cell range")
            if next_phase not in phases:
                phases.add(next_phase)
                pending.append(next_phase)
            rows.append({"state": name(phase), "symbol": f"{m}{a}{g}",
                         "output": str(y), "next": name(next_phase)})
    return Model({"schema": MODEL_SCHEMA, "states": [name(p) for p in phases],
                  "initial": name(phase0), "alphabet": [f"{m}{a}{g}" for m, a, g in columns],
                  "outputs": ["0", "1"], "terminal": {name(p): "unobserved" for p in phases},
                  "steps": rows, "binding": {
                      "adapter": "reachable states of require/source_cell only",
                      "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                      "carry_program": program,
                      "scope": "reviewed nonsign cell model; final physical carry is not observed"
                  }}).data


def pinned_model():
    path = Path(__file__).resolve().parents[1] / "graal" / "carry_kernel.py"
    source = path.read_bytes()
    require(hashlib.sha256(source).hexdigest() == PINNED_SOURCE_SHA256, "pinned native source changed")
    return native_model(source.decode())
