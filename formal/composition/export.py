"""Checked live certificates → deterministic Lean composition data.

Native source facts remain named assumptions. Every derived ground event and
every via-lemma link is retained. No producer, planner or solver is imported.
Source, guard, width and name mapping are checked Python adapter boundaries,
not claims about a verified JSON parser or verified source semantics.
"""

import argparse
import hashlib
import re
from copy import deepcopy
from pathlib import Path

from formal.ground.export import decoded_data, lean_list, n, ns
from formal.ground.export import export as ground_export
from formal.ground.export import render as render_ground
from research.applicable_summary.checker import check as check_summary
from research.applicable_summary.direct import check as check_direct
from research.ground_query.schema import canonical, digest, load_json, require
from research.signed_compact import dag
from research.source_lemmas.checker import load
from research.source_lemmas.context import prepare, target_context
from research.source_lemmas.terms import roots
from research.source_query.encoding import Graph


def numeric_term(value, symbols):
    require(type(value) is list and value and value[0] in symbols, "known closed symbol")
    return [symbols[value[0]], [numeric_term(t, symbols) for t in value[1:]]]


def numeric_pair(value, symbols):
    require(type(value) is list and len(value) == 2, "closed equality")
    return [numeric_term(t, symbols) for t in value]


def resolved(request):
    terms = []
    for node in request["nodes"]:
        terms.append([node["op"], [terms[i] for i in node["args"]]])
    return terms


class Builder:
    def __init__(self, sorts, signature):
        self.sort_ids = {s: i for i, s in enumerate(sorts)}
        self.symbol_ids = {s: i for i, s in enumerate(sorted(signature))}
        self.data = dict(
            sorts=len(sorts),
            signature=[
                dict(
                    args=[self.sort_ids[a] for a in signature[s]["args"]],
                    result=self.sort_ids[signature[s]["result"]],
                )
                for s in self.symbol_ids
            ],
            assumptions=[],
            entries=[],
            consumers=[],
        )
        self.indices, self.origins = {}, []

    def native(self, identity, claim, origin):
        index = len(self.data["assumptions"])
        self.data["assumptions"].append(numeric_pair(claim, self.symbol_ids))
        self.indices[identity] = len(self.data["entries"])
        self.data["entries"].append(dict(kind="native", index=index))
        self.origins.append(dict(index=index, identity=identity, **origin))

    def derived(self, identity, claim, premise_ids, via, request, certificate):
        data = decoded_data(request, certificate)
        require(data["binding"]["excluded_query_indices"] == [], "positive derivation required")
        require(
            data["request"]["signature"] == self.data["signature"]
            and data["binding"]["sort_ids"] == self.sort_ids
            and data["binding"]["symbol_ids"] == self.symbol_ids,
            "exact shared signature",
        )
        entry = dict(
            kind="derived",
            request=data["request"],
            certificate=data["certificate"],
            premises=[self.indices[i] for i in premise_ids],
            via=None if via is None else self.indices[via],
            claim=numeric_pair(claim, self.symbol_ids),
            query=0,
        )
        self.indices[identity] = len(self.data["entries"])
        self.data["entries"].append(entry)

    def consumer(self, identity, claim):
        self.data["consumers"].append(
            dict(index=self.indices[identity], claim=numeric_pair(claim, self.symbol_ids))
        )

    def finish(self, binding):
        return dict(
            packet=self.data,
            binding=dict(
                **binding,
                sort_ids=self.sort_ids,
                symbol_ids=self.symbol_ids,
                native_assumptions=self.origins,
                native_semantics="explicit theorem premises; source rules are not Lean-proved",
                adapter_trust="JSON, source/scope binding and symbolic-to-numeric name mapping",
            ),
        )


def export_ground(request, certificate):
    data, _ = ground_export(request, certificate, "ground_input")
    r = data["request"]
    terms = resolved(r)
    assumptions = [[terms[a], terms[b]] for a, b in r["equations"]]
    entries = [dict(kind="native", index=i) for i in range(len(assumptions))]
    consumers = []
    for i, (a, b) in enumerate(r["queries"]):
        claim = [terms[a], terms[b]]
        consumers.append(dict(index=len(entries), claim=claim))
        entries.append(
            dict(
                kind="derived",
                request=r,
                certificate=data["certificate"],
                premises=list(range(len(assumptions))),
                via=None,
                claim=claim,
                query=i,
            )
        )
    return dict(
        packet=dict(
            sorts=r["sorts"],
            signature=r["signature"],
            assumptions=assumptions,
            entries=entries,
            consumers=consumers,
        ),
        binding=dict(
            format="ground",
            **data["binding"],
            native_assumptions=[dict(index=i, equation=i) for i in range(len(assumptions))],
        ),
    )


def export_lemmas(source, batch, packet):
    presentation, results = load(source, batch, packet)
    require(
        results and all(r["status"] == "certified" for r in results),
        "composition export requires positive source consumers",
    )
    payload = dag.unpack(packet)
    ctx = presentation.context()
    builder = Builder(["Word", "Bool"], Graph(ctx).signature)
    cursor = 0
    for lemma in payload["E_plus"]:
        while cursor < lemma["native_count"]:
            row = payload["E"][cursor]
            builder.native(
                row["id"], row["claim"], dict(evidence=row["evidence"], scope=row["scope"])
            )
            cursor += 1
        epoch = dict(native=lemma["native_count"], lemmas=lemma["prior_lemmas"])
        claim = presentation.residual_claim(lemma["claim"], lemma["via_lemma"], epoch)
        req = presentation.request(claim, lemma["basis"], epoch)
        builder.derived(
            lemma["id"],
            lemma["claim"],
            lemma["basis"]["native"] + lemma["basis"]["lemmas"],
            lemma["via_lemma"],
            req,
            lemma["certificate"],
        )
    for row in payload["E"][cursor:]:
        builder.native(row["id"], row["claim"], dict(evidence=row["evidence"], scope=row["scope"]))
    ids = []
    for i, (request, item) in enumerate(zip(batch["requests"], payload["items"])):
        claim = roots(target_context(ctx, request))
        if item["kind"] == "cached_goal":
            identity = ids[item["previous"]]
        elif item["kind"] == "lemma":
            identity = item["lemma"]
        else:
            require(item["kind"] == "ground", "positive ground consumer")
            residual = presentation.residual_claim(claim, item["via_lemma"], item["epoch"])
            req = presentation.request(residual, item["basis"], item["epoch"])
            identity = "consumer:" + str(i)
            builder.derived(
                identity,
                claim,
                item["basis"]["native"] + item["basis"]["lemmas"],
                item["via_lemma"],
                req,
                item["certificate"],
            )
        ids.append(identity)
        builder.consumer(identity, claim)
    return builder.finish(
        dict(
            format="source_lemmas",
            source_sha256=hashlib.sha256(source.encode()).hexdigest(),
            batch_sha256=digest(batch),
            packet_sha256=digest(packet),
            scope=payload["scope"],
        )
    )


def export_direct(source, batch, data):
    results, _ = check_direct(source, batch, data)
    require(
        results and all(r["status"] == "certified" for r in results),
        "composition export requires positive direct consumers",
    )
    ctx, _ = prepare(source, batch)
    builder = Builder(["Word", "Bool"], Graph(ctx).signature)
    for node in data["nodes"]:
        if node["kind"] == "native":
            row = node["entry"]
            builder.native(
                node["id"],
                row["claim"],
                dict(entry_id=row["id"], evidence=row["evidence"], scope=row["scope"]),
            )
        else:
            builder.derived(
                node["id"],
                node["claim"],
                node["premises"],
                node["via"],
                node["request"],
                node["proof"],
            )
    ids = []
    for request, goal in zip(batch["requests"], data["goals"]):
        identity = ids[goal["previous"]] if goal["kind"] == "cached" else goal["node"]
        ids.append(identity)
        builder.consumer(identity, roots(target_context(ctx, request)))
    return builder.finish(
        dict(
            format="direct",
            source_sha256=hashlib.sha256(source.encode()).hexdigest(),
            batch_sha256=digest(batch),
            direct_sha256=digest(data),
            scope=data["scope"],
        )
    )


def export_summary(source, request, packet):
    checked = check_summary(source, request, packet)
    require(checked.result()["status"] == "certified", "positive SDK packet required")
    data = dag.unpack(packet)
    require(data["kind"] == "native_direct", "only direct signed SDK packets are supported")
    out = export_direct(source, request["query"], data["evidence"])
    out["binding"].update(
        format="summary_direct", request_sha256=digest(request), packet_sha256=digest(packet)
    )
    return out


def export_input(data):
    kind = data["format"]
    if kind == "ground":
        return export_ground(data["request"], data["certificate"])
    if kind == "source_lemmas":
        return export_lemmas(data["source"], data["request"], data["packet"])
    if kind == "direct":
        return export_direct(data["source"], data["request"], data["packet"])
    require(kind == "summary_direct", "supported format required")
    return export_summary(data["source"], data["request"], data["packet"])


def render_term(t):
    return "(.app " + n(t[0]) + " " + lean_list(render_term(c) for c in t[1]) + ")"


def render_pair(p):
    return "(" + render_term(p[0]) + ", " + render_term(p[1]) + ")"


def render(name, data, accepted=True):
    require(type(name) is str and re.fullmatch(r"[a-z][a-z0-9_]*", name), "Lean identifier")
    p = deepcopy(data["packet"])
    declarations, entries = [], []
    for i, e in enumerate(p["entries"]):
        if e["kind"] == "native":
            entries.append(".native " + n(e["index"]))
            continue
        require(e["kind"] == "derived", "composition rule")
        # Reuse PR50's deterministic syntax printer, but no standalone theorem
        # accepting the ground fragment with its derived premises as axioms.
        label = name + "_d" + str(i)
        text = render_ground(label, dict(request=e["request"], certificate=e["certificate"]))
        declarations.append(text[: text.index("theorem ")])
        via = "none" if e["via"] is None else "(some " + n(e["via"]) + ")"
        entries.append(
            ".derived ⟨"
            + ", ".join(
                [
                    label + "_request",
                    label + "_certificate",
                    ns(e["premises"]),
                    via,
                    render_pair(e["claim"]),
                    n(e["query"]),
                ]
            )
            + "⟩"
        )
    signature = lean_list("⟨" + ns(s["args"]) + ", " + n(s["result"]) + "⟩" for s in p["signature"])
    consumers = lean_list(
        "⟨" + n(g["index"]) + ", " + render_pair(g["claim"]) + "⟩" for g in p["consumers"]
    )
    declarations.append(
        f"def {name}_packet : QKFComposition.Packet :=\n"
        f"  ⟨{n(p['sorts'])}, {signature},\n"
        f"   {lean_list(render_pair(a) for a in p['assumptions'])},\n"
        f"   {lean_list(entries)},\n   {consumers}⟩\n"
        f"theorem {name}_{'accepted' if accepted else 'rejected'} :\n"
        f"    QKFComposition.check {name}_packet = {'true' if accepted else 'false'} := by decide +kernel\n"
    )
    return "\n".join(declarations)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--name", default="exported")
    args = parser.parse_args()
    decoded = export_input(load_json(args.input))
    args.output.write_text("import Composition\nopen QKFGround\n" + render(args.name, decoded))
    print(canonical(decoded["binding"]).decode())
