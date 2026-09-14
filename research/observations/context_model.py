"""Finite local constraints at shared cuts; no residual observation is supplied."""
from .model import digest, names, require

SCHEMA = "qkf-native-context-rows-v1"
CERT_SCHEMA = "qkf-derived-shared-context-v1"
ATOMIC_CERT_SCHEMA = "qkf-derived-shared-context-atomic-v1"
MAX_STATES = 4096
MAX_PRODUCT = 65536


class ContextModel:
    def __init__(self, data):
        require(type(data) is dict and set(data) == {
            "schema", "contexts", "controls", "alphabet", "initial_control",
            "bottom", "boundary", "rows", "binding"
        }, "context model fields")
        require(data["schema"] == SCHEMA, "context model schema")
        self.contexts = names(data["contexts"], 8)
        self.controls = names(data["controls"], 16)
        self.alphabet = names(data["alphabet"], 32)
        self.index = {s: i for i, s in enumerate(self.contexts)}
        self.top = (1 << len(self.contexts)) - 1
        self.initial = data["initial_control"]
        self.boundary = data["boundary"]
        require(type(self.initial) is str and self.initial in self.controls, "initial control")
        require(type(self.boundary) is str and self.boundary in self.contexts, "boundary context")
        bottom = data["bottom"]
        require(type(bottom) is list and all(type(s) is str and s in self.contexts for s in bottom)
                and len(bottom) == len(set(bottom)), "bottom contexts")
        self.bottom = sum(1 << self.index[s] for s in bottom)
        require(type(data["binding"]) is dict, "context source binding")
        rows = data["rows"]
        require(type(rows) is list and len(rows) == len(self.controls) * len(self.alphabet),
                "complete local constraint family")
        self.rows = {}
        for row in rows:
            require(type(row) is dict and set(row) == {"control", "symbol", "next_control", "edges"},
                    "local constraint fields")
            c, a, n = (row[k] for k in ("control", "symbol", "next_control"))
            require(all(type(s) is str for s in (c, a, n)) and c in self.controls
                    and a in self.alphabet and n in self.controls, "local constraint names")
            require((c, a) not in self.rows, "duplicate local constraint")
            require(type(row["edges"]) is list, "context edges")
            edges = {}
            for edge in row["edges"]:
                require(type(edge) is list and len(edge) == 2
                        and all(type(s) is str and s in self.contexts for s in edge), "context edge names")
                above, below = edge
                require(above not in edges, "local relation must be a partial function")
                edges[above] = below
            self.rows[c, a] = (n, edges)
        self.data = {"schema": SCHEMA, "contexts": self.contexts, "controls": self.controls,
                     "alphabet": self.alphabet, "initial_control": self.initial,
                     "bottom": sorted(bottom), "boundary": self.boundary, "binding": data["binding"],
                     "rows": [{"control": c, "symbol": a, "next_control": self.rows[c, a][0],
                               "edges": [list(e) for e in sorted(self.rows[c, a][1].items())]}
                              for c in self.controls for a in self.alphabet]}
        self.sha256 = digest(self.data)

    def members(self, mask):
        return [s for s in self.contexts if mask & (1 << self.index[s])]
