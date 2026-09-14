"""Reviewed descending comparison primitives, without the handwritten P observer.

The three-valued context vocabulary, suffix control and cut wiring are supplied
by this adapter. Only residual observations and loss witnesses are synthesized.
Trusted source function extraction is not a security sandbox or a Java parser.
"""
import ast
import hashlib
from copy import deepcopy
from pathlib import Path

from .context_model import ContextModel, SCHEMA
from .model import require

PINNED_COMMIT = "d7e631155b9382c787baf72a28b1e335a7074d7e"
PINNED_SOURCE_SHA256 = "11a4c2f4ced09fbeadf698e79d4347989f258bbf5f54a2cfb13a6f3906eb5460"
GUARD = ["and", ["optional"], ["comparison", [-1, 0]]]
RELATIONS = {-1: "less", 0: "equal", 1: "greater"}


def native_model(source, guard=None):
    guard = deepcopy(GUARD if guard is None else guard)
    tree = ast.parse(source)
    wanted = {"require", "compare", "prefix", "select"}
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    require(len(functions) == len(wanted) and {n.name for n in functions} == wanted,
            "exact descending primitive definitions")
    namespace = {}
    exec(compile(ast.Module(body=functions, type_ignores=[]), "descending_primitives", "exec"), namespace)
    compare, prefix, select = (namespace[n] for n in ("compare", "prefix", "select"))
    for r in RELATIONS:
        require(select(guard, False, r) is False, "guard must preserve fixed bits of the declared column domain")
    columns = [(a, o, u, y) for a, o in ((0, 0), (0, 1), (1, 0))
               for u in (0, 1) for y in range(a, a + o + 1)]
    rows = []
    for r in RELATIONS:
        for a, o, u, y in columns:
            edges = []
            for h in RELATIONS:
                through = prefix(h, y, u)
                trial = prefix(h, 1, u) or r
                require(type(through) is int and through in RELATIONS
                        and type(trial) is int and trial in RELATIONS, "native comparison range")
                selected = select(guard, o, trial)
                require(type(selected) is bool, "native selector range")
                if (a | int(selected)) == y:
                    edges.append([RELATIONS[h], RELATIONS[through]])
            nr = compare(a, u) or r
            require(type(nr) is int and nr in RELATIONS, "native suffix range")
            rows.append({"control": RELATIONS[r], "symbol": f"{a}{o}{u}{y}",
                         "next_control": RELATIONS[nr], "edges": edges})
    return ContextModel({"schema": SCHEMA, "contexts": list(RELATIONS.values()),
                         "controls": list(RELATIONS.values()),
                         "alphabet": [f"{a}{o}{u}{y}" for a, o, u, y in columns],
                         "initial_control": "equal", "bottom": list(RELATIONS.values()),
                         "boundary": "equal", "rows": rows, "binding": {
                             "adapter": "descending native compare/prefix/select only",
                             "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                             "guard": guard, "column_order": "low-to-high (a,optional,u,y)",
                             "scope": "unsigned comparison model with explicitly shared cuts"
                         }}).data


def pinned_model():
    path = Path(__file__).resolve().parents[1] / "graal/previous/row_kernel.py"
    source = path.read_bytes()
    require(hashlib.sha256(source).hexdigest() == PINNED_SOURCE_SHA256, "pinned descending source changed")
    return native_model(source.decode())
