"""Explicit fixture creation only; never imported by checker/replay.

Reproduce with the original PR49 artifact ZIP. The ordinary validation path
uses the committed inputs and does not run a producer or download artifacts.
"""

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from research.ground_query.producer import prove as prove_ground
from research.ground_query.schema import canonical, digest, require
from research.signed_compact import dag
from research.source_lemmas.checker import load
from research.source_lemmas.context import target_context
from research.source_lemmas.fixtures import DEFAULTS, MASK, PARITY, batch, goals
from research.source_lemmas.producer import prove
from research.source_lemmas.terms import roots

ROOT = Path(__file__).resolve().parent
ARTIFACT = 10671870725
ARCHIVE_SHA = "74a29fa33a5d819df4f9df712decf01e3b2745022a6d326b2a4b5f6821b35c29"
PR49 = "0be531350f1e062b04a26fd51915e443765026d5"


def freeze(archive):
    raw = archive.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == ARCHIVE_SHA, "original PR49 ZIP digest")
    inputs = {}
    for name in ("gap", "typed_binary", "shared_typed", "reverse_axioms"):
        parent = ROOT.parent / "ground/evidence"
        inputs["ground_" + name] = dict(
            format="ground",
            request=json.loads((parent / (name + ".request.json")).read_text()),
            certificate=json.loads((parent / (name + ".certificate.json")).read_text()),
            origin=dict(
                kind="preserved PR50 evidence", path=str(parent.relative_to(ROOT.parents[1]) / name)
            ),
        )
    for name, source, selected, width, route in (
        ("lemma_chain", MASK, goals()[:4], None, "reuse"),
        ("lemma_parity_fixed8", PARITY, goals()[:4], 8, "reuse"),
        ("lemma_repeats", MASK, [goals()[0]] * 3, None, "reuse"),
        ("lemma_none", MASK, goals()[:2], None, "no_lemmas"),
    ):
        request = batch(source, selected, width=width)
        packet, result, _ = prove(source, request, route=route, limits=DEFAULTS)
        require(all(g["status"] == "certified" for g in result["goals"]), "positive fixture")
        if name == "lemma_chain":
            presentation, _ = load(source, request, packet)
            data = dag.unpack(packet)
            # Promote a second actual checked goal, using the first lemma via
            # a residual proof. The next consumer then imports the second one.
            for goal_index in (1, 2):
                via = presentation.lemmas()[-1]["id"]
                claim = roots(
                    target_context(presentation.context(), request["requests"][goal_index])
                )
                epoch = presentation.epoch()
                basis = dict(
                    native=[x["id"] for x in presentation.native()],
                    lemmas=[x["id"] for x in presentation.lemmas()],
                )
                residual = presentation.residual_claim(claim, via, epoch)
                req = presentation.request(residual, basis, epoch)
                cert, _ = prove_ground(req, mode="entailment")
                item = dict(
                    kind="ground", basis=basis, epoch=epoch, via_lemma=via, certificate=cert
                )
                checked = presentation.verify(request["requests"][goal_index], item)
                if goal_index == 1:
                    presentation, lemma = presentation.promote(checked)
                    data["E_plus"].append(lemma)
                    data["items"][goal_index] = dict(kind="lemma", lemma=lemma["id"])
                else:
                    data["items"][goal_index] = item
            packet = dag.pack(data)
            load(source, request, packet)
        inputs[name] = dict(
            format="source_lemmas",
            source=source,
            request=request,
            packet=packet,
            origin=dict(
                kind="preserved PR44 producer plus explicit checked promotions",
                base="bee1a2ad64668d86054fa91ab4d23bd399bc4789",
                route=route,
            ),
        )
    with zipfile.ZipFile(archive) as z:
        require(z.read("revision.txt").decode().strip() == PR49, "PR49 engine identity")
        manifest = json.loads(z.read("comparison/MANIFEST.json"))
        for member, expected in manifest.items():
            require(
                hashlib.sha256(z.read("comparison/" + member)).hexdigest() == expected,
                "PR49 manifest: " + member,
            )
        case_member = "comparison/batch_mask_all_4/case.json"
        case = json.loads(z.read(case_member))
        for route in ("ordinary_no_lemmas", "ordinary_reuse", "query_no_lemmas", "query_reuse"):
            member = "comparison/batch_mask_all_4/emitted_" + route + "/audit.json"
            audit = json.loads(z.read(member))
            require(
                digest(audit["certificate"]) == audit["identity"]["certificate_sha256"],
                "PR49 delivery identity",
            )
            packets = audit["certificate"]["packets"]
            require(len(packets) == 1, "one summary per service delivery")
            inputs["pr49_" + route] = dict(
                format="summary_direct",
                source=case["source"],
                request=case["request"],
                packet=packets[0],
                origin=dict(
                    kind="original PR49 CI output",
                    engine=PR49,
                    artifact_id=ARTIFACT,
                    archive_sha256=ARCHIVE_SHA,
                    member=member,
                    member_sha256=hashlib.sha256(z.read(member)).hexdigest(),
                    case_member=case_member,
                    case_sha256=hashlib.sha256(z.read(case_member)).hexdigest(),
                    delivery_sha256=digest(audit["certificate"]),
                    packet_sha256=digest(packets[0]),
                ),
            )
    (ROOT / "inputs").mkdir(exist_ok=True)
    for name, data in inputs.items():
        (ROOT / "inputs" / (name + ".json")).write_bytes(canonical(data) + b"\n")
    return len(inputs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pr49_artifact", type=Path)
    args = parser.parse_args()
    print(freeze(args.pr49_artifact))
