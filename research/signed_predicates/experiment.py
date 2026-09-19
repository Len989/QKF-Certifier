"""Post-holdout development study for positive-only power-of-two predicates."""

import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess
import tempfile

from research.external.frozen_v2.experiment import checked_inputs, load, save
from research.observations.model import digest, require

from .checker import check
from .frontend import CONTRACT, GOAL_SCHEMA, select, target_value
from .producer import derive
from .semantics import evaluate

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / "research/external/frozen_v2"


def specification(entry, word_type):
    return {
        "schema": GOAL_SCHEMA,
        "contract": CONTRACT,
        "entry": entry,
        "word_type": word_type,
        "target": ["and", ["positive"], ["popcount_eq", 1]],
    }


CASES = (
    ("guava_long", "guava_long_math", "LongMath", "long", 64),
    ("guava_int", "guava_int_math", "IntMath", "int", 32),
    ("commons_long", "commons_arithmetic_utils", "ArithmeticUtils", "long", 64),
)


def population(width):
    mask = (1 << width) - 1
    xs = set(range(1 << 16))
    for k in range(width):
        bit = 1 << k
        xs.update({bit & mask, (bit - 1) & mask, (bit + 1) & mask, mask ^ bit})
    xs.update({0, 1, mask, 1 << (width - 1), (1 << (width - 1)) - 1})
    rng = random.Random(24001 + width)
    xs.update(rng.getrandbits(width) for _ in range(4096))
    return sorted(xs)


def native(declaration, method_name, word_type, width, xs):
    java, javac = shutil.which("java"), shutil.which("javac")
    require(java is not None and javac is not None, "JDK required for signed predicate validation")
    conversion = (
        "int x=(int)Long.parseUnsignedLong(s);"
        if word_type == "int"
        else "long x=Long.parseUnsignedLong(s);"
    )
    source = f"""import java.io.*;
public class SignedPredicateProbe {{
  {declaration}
  public static void main(String[] ignored) throws Exception {{
    BufferedReader r=new BufferedReader(new InputStreamReader(System.in));
    for(String s;(s=r.readLine())!=null;) {{
      {conversion}
      System.out.println(METHOD(x));
    }}
  }}
}}
"""
    payload = "".join(str(x) + "\n" for x in xs)
    with tempfile.TemporaryDirectory(prefix="qkf-signed-predicate-") as temp:
        root = Path(temp)
        path = root / "SignedPredicateProbe.java"
        path.write_text(source, encoding="utf-8")
        cp = subprocess.run(
            [javac, "--release", "17", str(path)],
            capture_output=True, text=True, timeout=45,
        )
        require(cp.returncode == 0, "signed predicate native compile: " + cp.stderr[-4000:])
        run = subprocess.run(
            [java, "-ea", "-cp", temp, "SignedPredicateProbe"],
            input=payload, capture_output=True, text=True, timeout=45,
        )
        require(run.returncode == 0, "signed predicate native run: " + run.stderr[-4000:])
    ys = run.stdout.splitlines()
    require(len(ys) == len(xs) and all(y in {"true", "false"} for y in ys),
            "one native signed predicate output")
    return [y == "true" for y in ys]


def run(inputs, output, *, replay=False):
    inputs, output = Path(inputs), Path(output)
    corpus = load(FROZEN / "CORPUS.json")
    texts, identities = checked_inputs(inputs, corpus)

    if replay:
        require(output.is_dir(), "existing signed predicate experiment")
    else:
        require(not output.exists(), "new signed predicate experiment directory")
        output.mkdir(parents=True)

    rows = {}
    for case_id, source_name, class_name, word_type, width in CASES:
        source = texts[source_name]
        goal = specification({"class": class_name, "method": "isPowerOfTwo"}, word_type)
        directory = output / case_id
        if replay:
            cert = json.loads((directory / "certificate.json").read_text())
            result = check(source, goal, cert)
            expected = json.loads((directory / "result.json").read_text())
            require(result == expected, "signed predicate replay identity: " + case_id)
            native_record = json.loads((directory / "native.json").read_text())
        else:
            cert, result = derive(source, goal)
            require(result["status"] == "certified", "signed external development proof: " + case_id)
            directory.mkdir()
            save(directory / "goal.json", goal)
            save(directory / "certificate.json", cert)
            save(directory / "result.json", result)

            body, _parameter, _final, declaration, _span = select(
                source, goal["entry"], word_type=word_type
            )
            require(body, "selected signed predicate body")
            xs = population(width)
            ys = native(declaration, goal["entry"]["method"], word_type, width, xs)
            ir = cert["source"]["ir"]
            mismatches = 0
            for x, actual in zip(xs, ys):
                sign = (x >> (width - 1)) & 1
                expected_target = target_value(goal["target"], x.bit_count(), sign)
                expected_ir = evaluate(ir, x, width)
                if actual != expected_target or actual != expected_ir:
                    mismatches += 1
            native_record = {
                "inputs": len(xs),
                "mismatches": mismatches,
                "whole_original_blob_selected_method": True,
                "width": width,
            }
            require(mismatches == 0, "native/source/target signed predicate agreement")
            save(directory / "native.json", native_record)

        rows[case_id] = {
            "status": result["status"],
            "word_type": word_type,
            "source_sha256": result["source_sha256"],
            "certificate_sha256": digest(cert),
            "source_states": result["source"]["native_states"],
            "classes": result["source"]["classes"],
            "product_states": result["product_states"],
            "native_inputs": native_record["inputs"],
            "native_mismatches": native_record["mismatches"],
        }

    summary = {
        "schema": "qkf-signed-predicate-development-v1",
        "development_after_frozen_v2": True,
        "frozen_v2_historical_result_unchanged": True,
        "cases": rows,
        "counts": {"certified": sum(r["status"] == "certified" for r in rows.values())},
        "total_native_inputs": sum(r["native_inputs"] for r in rows.values()),
        "native_mismatches": sum(r["native_mismatches"] for r in rows.values()),
        "scope": (
            "post-holdout development reuse of three measured gap methods; "
            "not a new holdout and not a revision of frozen_v2 results"
        ),
    }
    if replay:
        saved = json.loads((output / "SUMMARY.json").read_text())
        require(summary == saved, "signed predicate replay summary")
    else:
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
    print(json.dumps(run(args.inputs, args.output, replay=args.replay), sort_keys=True))


if __name__ == "__main__":
    main()
