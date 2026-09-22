"""Recheck frozen inputs and regenerate all Lean data without proof search."""

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from research.ground_query.schema import canonical, load_json, require

from .export import export_input, render

ROOT = Path(__file__).resolve().parent


def negatives(positive):
    ground = positive["ground_gap"]
    chain = positive["lemma_chain"]

    def mutate(name, source, change):
        d = deepcopy(source)
        change(d["packet"])
        return "reject_" + name, d

    first = len(ground["packet"]["assumptions"])
    yield mutate(
        "future_premise",
        ground,
        lambda p: p["entries"][first]["premises"].__setitem__(0, first + 1),
    )
    yield mutate(
        "self_support", ground, lambda p: p["entries"][first]["premises"].__setitem__(0, first)
    )
    yield mutate("missing_foundation", ground, lambda p: p["assumptions"].pop())
    yield mutate("wrong_premise_endpoint", ground, lambda p: p["assumptions"][0].reverse())
    yield mutate(
        "wrong_signature",
        ground,
        lambda p: p["entries"][first]["request"]["signature"][0].update(result=1),
    )
    yield mutate("wrong_sort_count", ground, lambda p: p.update(sorts=2))
    yield mutate(
        "wrong_ground_axiom",
        ground,
        lambda p: p["entries"][first]["certificate"]["events"][0].update(equation=99),
    )
    yield mutate(
        "missing_ground_event", ground, lambda p: p["entries"][first]["certificate"]["events"].pop()
    )
    yield mutate("wrong_goal_index", ground, lambda p: p["entries"][first].update(query=99))
    yield mutate("wrong_consumer", ground, lambda p: p["consumers"][0]["claim"].reverse())
    yield mutate(
        "missing_consumer_foundation", ground, lambda p: p["consumers"][0].update(index=999)
    )
    via_index = next(
        i for i, e in enumerate(chain["packet"]["entries"]) if e.get("via") is not None
    )
    yield mutate("future_via", chain, lambda p: p["entries"][via_index].update(via=via_index + 1))
    yield mutate("self_via", chain, lambda p: p["entries"][via_index].update(via=via_index))
    yield mutate("via_left_endpoint", chain, lambda p: p["entries"][via_index]["claim"].reverse())
    yield mutate("lost_via", chain, lambda p: p["entries"][via_index].update(via=None))
    yield mutate(
        "false_residual",
        chain,
        lambda p: p["entries"][via_index]["request"]["queries"][0].reverse(),
    )
    yield mutate(
        "false_late_lemma",
        chain,
        lambda p: p["entries"][via_index]["certificate"]["goals"][0].update(path=[]),
    )


def expected_files():
    positive = {
        p.stem: export_input(load_json(p)) for p in sorted((ROOT / "inputs").glob("*.json"))
    }
    require(len(positive) == 12, "complete frozen input population")
    files, cases, text = (
        {},
        [],
        [
            "import Composition\nopen QKFGround\nnamespace QKFComposition.Examples\n",
            "set_option maxRecDepth 20000\nset_option maxHeartbeats 4000000\n",
        ],
    )
    for accepted, entries in ((True, positive.items()), (False, negatives(positive))):
        for name, data in entries:
            path = "evidence/" + name + ".decoded.json"
            files[path] = canonical(data) + b"\n"
            text.append(render(name, data, accepted))
            p = data["packet"]
            cases.append(
                dict(
                    name=name,
                    expected=accepted,
                    file=path,
                    assumptions=len(p["assumptions"]),
                    entries=len(p["entries"]),
                    consumers=len(p["consumers"]),
                    via_links=sum(e.get("via") is not None for e in p["entries"]),
                    ground_events=sum(
                        len(e.get("certificate", {}).get("events", [])) for e in p["entries"]
                    ),
                )
            )
    text.append("end QKFComposition.Examples\n")
    files["CompositionExamples.lean"] = "\n".join(text).encode()
    manifest = dict(
        schema="qkf-composition-fixtures-v1",
        cases=cases,
        positive_count=len(positive),
        negative_count=sum(not c["expected"] for c in cases),
        inputs={
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / "inputs").glob("*.json"))
        },
        outputs={name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
    )
    files["FIXTURES.json"] = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode()
    return files


def regenerate(check_only=False):
    files = expected_files()
    actual = {"evidence/" + p.name for p in (ROOT / "evidence").glob("*.json")}
    expected = {p for p in files if p.startswith("evidence/")}
    require(not actual - expected, "unexpected stale composition evidence")
    for name, raw in files.items():
        path = ROOT / name
        if check_only:
            require(path.is_file() and path.read_bytes() == raw, "fixture/export drift: " + name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    return json.loads(files["FIXTURES.json"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    result = regenerate(parser.parse_args().check)
    print(json.dumps({k: result[k] for k in ("positive_count", "negative_count")}))
