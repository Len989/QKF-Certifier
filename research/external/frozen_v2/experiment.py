"""Execute the preregistered inference holdout without changing its engine."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False)
        stream.write("\n")


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def check_engine():
    frozen = load(HERE / "ENGINE.json")
    actual = {}
    for rel, expected in frozen["git_blobs"].items():
        raw = (ROOT / rel).read_bytes()
        found = git_blob(raw)
        require(found == expected, "frozen inference engine changed: " + rel)
        actual[rel] = found
    require(len(actual) == frozen["file_count"], "frozen engine file count")
    return {
        "commit": frozen["commit"],
        "tree": frozen["tree"],
        "file_count": len(actual),
        "git_blobs": actual,
    }


COMMENTS = re.compile(r"/\*[\s\S]*?\*/|//[^\n]*")
UNARY = re.compile(
    r"public\s+static\s+(?:final\s+)?(boolean|int|long)\s+"
    r"([A-Za-z_$][A-Za-z0-9_$]*)\s*\(\s*(?:final\s+)?"
    r"(int|long)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\)\s*\{"
)


def enumerate_methods(source_name, text, entry_class):
    code = COMMENTS.sub(" ", text)
    return [
        {
            "id": source_name + "." + m.group(2),
            "source": source_name,
            "method": m.group(2),
            "entry_class": entry_class,
            "parameter_type": m.group(3),
            "return_type": m.group(1),
        }
        for m in UNARY.finditer(code)
    ]


def checked_inputs(input_dir, corpus):
    input_dir = Path(input_dir)
    identities = load(input_dir / "IDENTITIES.json")
    require(set(identities) == set(corpus["sources"]), "complete holdout source identities")
    texts = {}
    for name, spec in corpus["sources"].items():
        raw = (input_dir / (name + ".java")).read_bytes()
        require(len(raw) <= corpus["budgets"]["source_bytes"], "holdout source byte budget")
        require(git_blob(raw) == spec["blob"], "holdout source blob changed: " + name)
        require(identities[name]["blob"] == spec["blob"], "saved holdout identity changed")
        texts[name] = raw.decode("utf-8")
    observed = []
    for name, spec in corpus["sources"].items():
        observed += enumerate_methods(name, texts[name], spec["class"])
    frozen = [
        {k: row[k] for k in (
            "id", "source", "method", "entry_class", "parameter_type", "return_type"
        )}
        for row in corpus["population"]
    ]
    require(observed == frozen, "holdout structural denominator differs from preregistration")
    return texts, identities


def source_attempt(case, source):
    entry = {"class": case["entry_class"], "method": case["method"]}
    try:
        if case["return_type"] == "boolean":
            from research.wordexpr.predicate_frontend import read_source
            ir = read_source(source, entry, case["parameter_type"])
            return {
                "status": "source_parsed",
                "profile": "predicate",
                "ir_sha256": digest(ir),
                "nodes": len(ir["nodes"]),
            }
        if case["return_type"] == "long" and case["parameter_type"] == "long":
            from research.wordexpr.frontend import read_source
            ir = read_source(source, entry)
            return {
                "status": "source_parsed",
                "profile": "wordexpr",
                "ir_sha256": digest(ir),
                "nodes": len(ir["nodes"]),
            }
        return {
            "status": "no_source_profile",
            "reason": "accepted word-result source frontend is long-to-long; predicate frontend requires boolean result",
        }
    except Exception as exc:
        from research.wordexpr.frontend import Unsupported
        if isinstance(exc, Unsupported):
            return {
                "status": "source_unsupported",
                "profile": "predicate" if case["return_type"] == "boolean" else "wordexpr",
                "reason": str(exc),
            }
        raise


def target_attempt(case, source, source_result):
    target = case["target"]
    if target is None:
        return {
            "status": "no_supported_target_language",
            "reason": case["target_reason"],
            "certificate": None,
            "result": None,
        }
    if source_result["status"] != "source_parsed":
        return {
            "status": source_result["status"],
            "reason": source_result.get("reason"),
            "certificate": None,
            "result": None,
        }
    from research.inference.producer import InferenceFailure
    from research.inference.v2_producer import infer
    try:
        cert, result = infer(
            source,
            target,
            max_features=128,
            max_target_states=8192,
        )
    except InferenceFailure as exc:
        return {
            "status": "budget_exhausted",
            "reason": str(exc),
            "certificate": None,
            "result": None,
        }
    require(result["status"] in {"certified", "refuted"}, "holdout target verdict")
    return {
        "status": result["status"],
        "reason": result.get("target_reason"),
        "certificate": cert,
        "result": result,
    }


def native_kilim(input_dir, output):
    java, javac = shutil.which("java"), shutil.which("javac")
    if not java or not javac:
        return {"status": "unavailable", "is_proof": False}
    raw = (Path(input_dir) / "kilim_mpsc_queue.java").read_bytes()
    text = raw.decode("utf-8")
    signature = "public static boolean isPowerOf2(final int value)"
    start = text.index(signature)
    brace = text.index("{", start)
    depth, end = 0, brace
    while end < len(text):
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
        if depth == 0:
            break
    require(depth == 0, "closed Kilim target declaration")
    declaration = text[start:end]
    rng = random.Random(23001)
    xs = set(range(1 << 16))
    xs.update(rng.getrandbits(32) for _ in range(4096))
    xs.update({0, 1, 2, 3, 0x7fffffff, 0x80000000, 0xffffffff})
    xs = sorted(xs)
    harness = """import java.io.*;
public class HoldoutProbe {
  DECLARATION
  public static void main(String[] ignored) throws Exception {
    BufferedReader r = new BufferedReader(new InputStreamReader(System.in));
    for (String s; (s = r.readLine()) != null; ) {
      int x = (int)Long.parseUnsignedLong(s);
      System.out.println(isPowerOf2(x));
    }
  }
}
""".replace("DECLARATION", declaration)
    with tempfile.TemporaryDirectory(prefix="qkf-holdout-kilim-") as tmp:
        root = Path(tmp)
        probe = root / "HoldoutProbe.java"
        probe.write_text(harness, encoding="utf-8")
        cp = subprocess.run(
            [javac, "--release", "17", str(probe)],
            capture_output=True, text=True, timeout=45,
        )
        require(cp.returncode == 0, "Kilim holdout native compile: " + cp.stderr[-4000:])
        ip = "".join(str(x) + "\n" for x in xs)
        run = subprocess.run(
            [java, "-ea", "-cp", str(root), "HoldoutProbe"],
            input=ip, capture_output=True, text=True, timeout=45,
        )
        require(run.returncode == 0, "Kilim holdout native run: " + run.stderr[-4000:])
    ys = run.stdout.splitlines()
    require(len(ys) == len(xs) and all(y in {"true", "false"} for y in ys),
            "one Boolean Kilim result per input")
    bad = []
    for x, y in zip(xs, ys):
        expected = x.bit_count() <= 1
        if (y == "true") != expected:
            bad.append({"input": x, "actual": y == "true", "expected": expected})
    result = {
        "status": "matched" if not bad else "mismatch",
        "inputs": len(xs),
        "mismatches": len(bad),
        "first_mismatches": bad[:5],
        "is_proof": False,
        "target": "popcount_le(1) over 32-bit patterns",
        "whole_class": False,
        "compiled_input": "exact extracted preregistered method declaration",
        "declaration_sha256": hashlib.sha256(declaration.encode("utf-8")).hexdigest(),
    }
    save(Path(output) / "NATIVE_KILIM.json", result)
    return result


def execute(input_dir, output, *, replay=False):
    corpus = load(HERE / "CORPUS.json")
    engine = check_engine()
    texts, identities = checked_inputs(input_dir, corpus)
    output = Path(output)
    if replay:
        require(output.is_dir(), "existing holdout output for replay")
    else:
        require(not output.exists(), "new holdout output directory")
        output.mkdir(parents=True)
        save(output / "ENGINE_ACTUAL.json", engine)
        save(output / "SOURCE_IDENTITIES.json", identities)

    cases = {}
    for case in corpus["population"]:
        case_id = case["id"]
        source = texts[case["source"]]
        source_result = source_attempt(case, source)
        directory = output / "cases" / case_id
        if replay:
            saved = load(directory / "CASE.json")
            require(saved["source"] == source_result, "replayed source classification: " + case_id)
            target_status = saved["target"]["status"]
            if saved["target"].get("certificate") is not None:
                from research.inference.v2_checker import check
                actual = check(source, case["target"], saved["target"]["certificate"])
                require(digest(actual) == digest(saved["target"]["result"]),
                        "replayed holdout certificate: " + case_id)
                require(actual["status"] == target_status, "replayed holdout verdict: " + case_id)
            target_record = saved["target"]
        else:
            attempted = target_attempt(case, source, source_result)
            target_record = {
                "status": attempted["status"],
                "reason": attempted["reason"],
                "certificate": attempted["certificate"],
                "result": attempted["result"],
            }
            save(directory / "CASE.json", {
                "id": case_id,
                "source": source_result,
                "target_registered": case["target"] is not None,
                "target": target_record,
            })
        cases[case_id] = {
            "source_status": source_result["status"],
            "target_registered": case["target"] is not None,
            "target_status": target_record["status"],
            "target_reason": target_record.get("reason"),
        }

    source_counts = dict(Counter(row["source_status"] for row in cases.values()))
    target_counts = dict(Counter(row["target_status"] for row in cases.values()))
    require(len(cases) == 15, "complete frozen holdout denominator")
    require(sum(source_counts.values()) == 15 and sum(target_counts.values()) == 15,
            "complete holdout classifications")
    allowed_source = {"source_parsed", "source_unsupported", "no_source_profile"}
    allowed_target = {
        "certified", "refuted", "source_unsupported", "budget_exhausted",
        "no_supported_target_language", "no_source_profile",
    }
    require(set(source_counts) <= allowed_source, "no holdout source internal error")
    require(set(target_counts) <= allowed_target, "no holdout target internal error")

    summary = {
        "schema": "qkf-inference-holdout-result-v1",
        "frozen_engine_commit": corpus["frozen_engine_commit"],
        "frozen_engine_tree": corpus["frozen_engine_tree"],
        "source_methods": len(cases),
        "registered_targets": sum(row["target_registered"] for row in cases.values()),
        "source_counts": source_counts,
        "target_counts": target_counts,
        "cases": cases,
        "no_tuning_after_first_run": True,
        "scope": "fresh external holdout; denominator includes unsupported and no-target methods",
    }
    if replay:
        saved_summary = load(output / "SUMMARY.json")
        summary["native_target_validation"] = saved_summary["native_target_validation"]
        require(digest(summary) == digest(saved_summary),
                "holdout replay summary identity")
    else:
        native = native_kilim(input_dir, output)
        require(native["status"] == "matched", "registered Kilim target native validation")
        summary["native_target_validation"] = native
        save(output / "SUMMARY.json", summary)
        save(output / "MANIFEST.json", {
            p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(output.rglob("*")) if p.is_file()
        })
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(args.inputs, args.output, replay=args.replay)
    except Exception as exc:
        print(json.dumps({"status": "internal_error", "error": type(exc).__name__,
                          "message": str(exc)}, sort_keys=True))
        return 70
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
