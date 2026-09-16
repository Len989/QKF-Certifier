"""Frozen direct-source applicability study; native tests never certify QKF goals.

Full mode requires complete original Git blobs. Slice mode is explicitly
provisional: it accepts reviewed connector excerpts, not full-blob verification.
Neither mode changes the frozen engine or invents a goal for an unrelated method.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MASK = (1 << 64) - 1


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path = Path(path)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def check_engine(root=ROOT):
    expected = load(HERE / "ENGINE.json")
    actual = {str(p.relative_to(root)): sha(p.read_bytes())
              for prefix in expected["roots"]
              for p in sorted((root / prefix).rglob("*" + expected["suffix"]))
              if expected["exclude_directory"] not in p.parts and "__pycache__" not in p.parts}
    require(len(actual) == expected["file_count"], "frozen engine file set changed")
    require(sha(canonical(actual)) == expected["sha256"], "frozen engine bytes changed")
    return actual


# Ignore comments and string/character literals only for locating braces.
# Return substrings from the untouched original text, never regenerated Java.
LEXICAL_IGNORES = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', re.S)


def lexical_code(source):
    return LEXICAL_IGNORES.sub(lambda m: "".join("\n" if x == "\n" else " " for x in m.group()), source)


def extract_method(source, method, parameters):
    code = lexical_code(source)
    signature = (r"\bpublic\s+static\s+(?:long|int|boolean)\s+" + re.escape(method)
                 + r"\s*\(\s*" + r"\s+".join(re.escape(t) for t in parameters.split()) + r"\s*\)\s*\{")
    matches = list(re.finditer(signature, code))
    require(len(matches) == 1, "exactly one selected public static declaration: " + method)
    match = matches[0]
    depth = 1
    end = match.end()
    while depth and end < len(code):
        depth += (code[end] == "{") - (code[end] == "}")
        end += 1
    require(depth == 0, "closed selected declaration")
    return source[match.start():end], {"start_character": match.start(), "end_character": end,
        "start_line": source.count("\n", 0, match.start()) + 1,
        "end_line": source.count("\n", 0, end) + 1}


def check_blob(raw, identity):
    require(len(raw) <= load(HERE / "CORPUS.json")["budget"]["source_bytes_limit"], "source size")
    actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    require(actual == identity["blob"], "original Git blob differs: " + identity["path"])
    return {**identity, "sha256": sha(raw), "bytes": len(raw), "git_blob_verified": True}


PROBE = '''import json, sys
from pathlib import Path
from research.observations.run_package import VALIDATION_ERRORS
profile, path = sys.argv[1:]
if profile == "ascending":
    from research.observations.ascending_source import read_source
else:
    from research.observations.java_words import read_source
try:
    result = read_source(Path(path).read_bytes().decode("utf-8"))
    outcome = {"status": "source_parsed", "schema": result.get("schema"), "is_proof": False}
except VALIDATION_ERRORS as exc:
    outcome = {"status": "source_unsupported", "exception": type(exc).__name__, "reason": str(exc), "is_proof": False}
except Exception as exc:
    outcome = {"status": "internal_error", "exception": type(exc).__name__, "reason": str(exc), "is_proof": False}
print(json.dumps(outcome, sort_keys=True))
'''


def child(argv, timeout, *, stdin=None, cwd=ROOT):
    started = time.perf_counter()
    try:
        result = subprocess.run(argv, input=stdin, cwd=cwd, capture_output=True, text=True,
                                timeout=timeout, env={**os.environ, "PYTHONPATH": str(ROOT)})
        return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr,
                "seconds": time.perf_counter() - started, "timeout": False}
    except subprocess.TimeoutExpired as exc:
        def text(value):
            return value.decode(errors="replace") if isinstance(value, bytes) else (value or "")
        return {"returncode": None, "stdout": text(exc.stdout), "stderr": text(exc.stderr),
                "seconds": time.perf_counter() - started, "timeout": True}


def probe(profile, source_path, timeout):
    result = child([sys.executable, "-O", "-c", PROBE, profile, str(source_path)], timeout)
    if result["timeout"]:
        outcome = {"status": "timeout", "is_proof": False}
    elif result["returncode"] != 0:
        outcome = {"status": "process_error", "is_proof": False}
    else:
        try:
            outcome = json.loads(result["stdout"])
        except json.JSONDecodeError:
            outcome = {"status": "invalid_process_output", "is_proof": False}
    return {"outcome": outcome, "process": result}


def signed(n, width=64):
    n &= (1 << width) - 1
    return n if n < (1 << (width - 1)) else n - (1 << width)


def words(config):
    n = 1 << config["small_unsigned_exhaustive_bits"]
    values = set(range(n)) | {(-x) & MASK for x in range(n)}
    for bit in range(64):
        for x in ((1 << bit) - 1, 1 << bit, (1 << bit) + 1):
            values.add(x & MASK)
            values.add((~x) & MASK)
    rng = random.Random(config["random_seed"])
    values.update(rng.getrandbits(64) for _ in range(config["random_words"]))
    return sorted(values)


def inputs(case, config):
    if case["method"] == "interleave":
        n = 1 << config["interleave_small_bits"]
        pairs = {(a, b) for a in range(n) for b in range(n)}
        edges = (0, 1, (1 << 31) - 1, 1 << 31, (1 << 32) - 1)
        pairs.update((a, b) for a in edges for b in edges)
        rng = random.Random(config["random_seed"])
        pairs.update((rng.getrandbits(32), rng.getrandbits(32)) for _ in range(config["random_words"]))
        return [list(p) for p in sorted(pairs)]
    population = words(config)
    if case["method"] == "nextHighestPowerOfTwo":
        low, high = config["power_of_two_domain"]
        population = [x for x in population if low <= x <= high]
    return [[x] for x in population]


def oracle(name, args):
    x = args[0]
    if name == "highestOneBit":
        return 0 if x == 0 else 1 << (x.bit_length() - 1)
    if name == "lowestOneBit":
        return 0 if x == 0 else 1 << next(i for i in range(64) if (x >> i) & 1)
    if name == "numberOfLeadingZeros":
        return 64 - x.bit_length()
    if name == "numberOfTrailingZeros":
        return next((i for i in range(64) if (x >> i) & 1), 64)
    if name == "bitCount":
        return sum((x >> i) & 1 for i in range(64))
    if name == "reverseBytes":
        return int.from_bytes(x.to_bytes(8, "little"), "big")
    if name == "nextHighestPowerOfTwo":
        require(0 <= x <= 1 << 62, "power-of-two oracle input domain")
        return 0 if x == 0 else 1 << (x - 1).bit_length()
    if name == "interleave":
        return sum((((args[j] >> i) & 1) << (2 * i + j)) for i in range(32) for j in range(2))
    if name == "deinterleave":
        return sum(((x >> (2 * i)) & 1) << i for i in range(32))
    if name == "flipFlop":
        return sum(((x >> i) & 1) << (i ^ 1) for i in range(64))
    if name == "zigZagEncode":
        y = signed(x)
        return 2 * y if y >= 0 else -2 * y - 1
    if name == "zigZagDecode":
        return ((x // 2) if x % 2 == 0 else -(x // 2) - 1) & MASK
    raise ValueError("unknown independent oracle")


# These are explicitly declared wrapper dependencies, not edited method bodies.
CONSTANTS = '''private static final long MAGIC0 = 0x5555555555555555L;
  private static final long MAGIC1 = 0x3333333333333333L;
  private static final long MAGIC2 = 0x0F0F0F0F0F0F0F0FL;
  private static final long MAGIC3 = 0x00FF00FF00FF00FFL;
  private static final long MAGIC4 = 0x0000FFFF0000FFFFL;
  private static final long MAGIC5 = 0x00000000FFFFFFFFL;
  private static final long MAGIC6 = 0xAAAAAAAAAAAAAAAAL;
  private static final long SHIFT0 = 1;
  private static final long SHIFT1 = 2;
  private static final long SHIFT2 = 4;
  private static final long SHIFT3 = 8;
  private static final long SHIFT4 = 16;'''


def native_run(corpus, slices, output):
    if not shutil.which("java") or not shutil.which("javac"):
        return {"status": "unavailable", "is_proof": False}
    work = output / "native"
    work.mkdir()
    for source, cls in (("jdk_long", "JdkSlice"), ("lucene_bits", "LuceneSlice")):
        deps = "public static final long MIN_VALUE = 0x8000000000000000L;" if source == "jdk_long" else CONSTANTS
        methods = "\n\n".join(slices[c["id"]] for c in corpus["population"] if c["source"] == source)
        notice_path = output / "provenance" / ("JDK_NOTICE.txt" if source == "jdk_long" else "LUCENE_NOTICE.txt")
        if notice_path.exists():
            notice = notice_path.read_text()
        else:
            raw_path = output / "provenance" / (source + ".java")
            original = raw_path.read_text() if raw_path.exists() else ""
            notice = original[:original.find("*/") + 2] + "\n" if original.startswith("/*") else ""
        code = notice + "// Extracted declarations; not a whole-library build.\nclass " + cls + " {\n" + deps + "\n" + methods + "\n}\n"
        (work / (cls + ".java")).write_text(code)
    arms = []
    for i, case in enumerate(corpus["population"]):
        cls = "JdkSlice" if case["source"] == "jdk_long" else "LuceneSlice"
        call_args = "(int)a, (int)b" if case["method"] == "interleave" else "a"
        arms.append(f'case {i}: y = {cls}.{case["method"]}({call_args}); break;')
    harness = '''import java.io.*;
public class NativeProbe {
 public static void main(String[] ignored) throws Exception {
  BufferedReader r = new BufferedReader(new InputStreamReader(System.in));
  BufferedWriter w = new BufferedWriter(new OutputStreamWriter(System.out));
  String line;
  while ((line = r.readLine()) != null) {
   String[] p = line.split(" ");
   int id = Integer.parseInt(p[0]);
   long a = Long.parseUnsignedLong(p[1]), b = Long.parseUnsignedLong(p[2]);
   long y;
   switch(id) { ARMS default: throw new IllegalArgumentException(); }
   w.write(Long.toUnsignedString(y)); w.newLine();
  }
  w.flush();
 }
}
'''.replace("ARMS", " ".join(arms))
    (work / "NativeProbe.java").write_text(harness)
    compiled = child(["javac", "--release", "17", "JdkSlice.java", "LuceneSlice.java", "NativeProbe.java"],
                     corpus["budget"]["native_compile_timeout_seconds"], cwd=work)
    save(work / "compile.json", compiled)
    if compiled["timeout"] or compiled["returncode"] != 0:
        return {"status": "compile_timeout" if compiled["timeout"] else "compile_error", "is_proof": False}
    populations = [inputs(case, corpus["native"]) for case in corpus["population"]]
    records = [(i, args) for i, pop in enumerate(populations) for args in pop]
    stdin = "".join(f'{i} {a[0]} {a[1] if len(a) == 2 else 0}\n' for i, a in records)
    (work / "inputs.txt").write_text(stdin)
    executed = child(["java", "-ea", "-cp", str(work), "NativeProbe"],
                     corpus["budget"]["native_execution_timeout_seconds"], stdin=stdin, cwd=work)
    (work / "outputs.txt").write_text(executed["stdout"])
    save(work / "process.json", {k: v for k, v in executed.items() if k != "stdout"})
    if executed["timeout"] or executed["returncode"] != 0:
        return {"status": "execution_timeout" if executed["timeout"] else "execution_error", "is_proof": False}
    lines = executed["stdout"].splitlines()
    require(len(lines) == len(records), "one native output for every input")
    results, offset = {}, 0
    for case, pop in zip(corpus["population"], populations):
        actual = [int(x) for x in lines[offset:offset + len(pop)]]
        expected = [oracle(case["method"], a) for a in pop]
        bad = [{"input": a, "actual": y, "expected": z} for a, y, z in zip(pop, actual, expected) if y != z]
        results[case["id"]] = {"inputs": len(pop), "mismatches": len(bad), "first_mismatches": bad[:5],
                               "inputs_sha256": sha(canonical(pop)), "outputs_sha256": sha(canonical(actual))}
        offset += len(pop)
    save(work / "RESULTS.json", results)
    return {"status": "matched" if all(r["mismatches"] == 0 for r in results.values()) else "mismatch",
            "total_inputs": len(records), "cases": results, "is_proof": False,
            "host_dependencies": ["Integer.numberOfLeadingZeros", "Integer.numberOfTrailingZeros"],
            "java": child(["java", "-version"], 10)["stderr"],
            "javac": child(["javac", "-version"], 10)["stdout"]}


def calibrate(directory, output, corpus):
    # Complete calibration originals are already available in prior CI artifacts.
    texts = {}
    for name in ("graal_control", "jdk_mask_control"):
        raw = (directory / (name + ".java")).read_bytes()
        check_blob(raw, corpus["sources"][name])
        texts[name] = raw.decode("utf-8")
    from research.observations.upstream_transfer import SEPARATOR, goal
    source = texts["graal_control"] + SEPARATOR + texts["jdk_mask_control"]
    result = {}
    dest = output / "calibration"
    dest.mkdir()
    (dest / "source.java").write_bytes(source.encode())
    for profile, claim in corpus["controls"]:
        name = profile + "." + claim
        spec = goal(profile, claim)
        spec_path = dest / (name + ".goal.json")
        save(spec_path, spec)
        path = dest / name
        made = child([sys.executable, "-m", "research.observations.run", "verify", str(dest / "source.java"),
                      "--spec", str(spec_path), "--profile", profile, "--output", str(path)],
                     corpus["budget"]["control_verify_timeout_seconds"])
        save(dest / (name + ".generation.json"), made)
        if made["timeout"] or made["returncode"] not in (0, 1):
            result[name] = {"status": "calibration_incomplete", "returncode": made["returncode"]}
            continue
        checked = child([sys.executable, "-O", "-m", "research.observations.run", "check",
                         str(dest / "source.java"), "--spec", str(spec_path),
                         "--package", str(path / "package.json")], corpus["budget"]["control_verify_timeout_seconds"])
        save(dest / (name + ".replay.json"), checked)
        require(not checked["timeout"] and checked["returncode"] == made["returncode"], "calibration replay")
        final = json.loads(checked["stdout"])
        result[name] = {"status": final["status"], "package_sha256": sha((path / "package.json").read_bytes())}
    return result


def execute(input_dir, output, *, slices_mode=False):
    corpus = load(HERE / "CORPUS.json")
    engine = check_engine()
    require(not output.exists(), "output directory must be new")
    output.mkdir(parents=True)
    save(output / "ENGINE_ACTUAL.json", engine)
    for f in ("CORPUS.json", "ENGINE.json", "PROTOCOL.md"):
        shutil.copyfile(HERE / f, output / f)
    originals, provenance, slices = {}, {}, {}
    if slices_mode:
        stated = {r["id"]: r for r in load(input_dir / "SLICES.json")}
        require(set(stated) == {c["id"] for c in corpus["population"]}, "complete slice population")
    else:
        for name in ("jdk_long", "lucene_bits"):
            raw = (input_dir / (name + ".java")).read_bytes()
            provenance[name] = check_blob(raw, corpus["sources"][name])
            originals[name] = raw.decode("utf-8")
    prov = output / "provenance"
    prov.mkdir()
    for extra in input_dir.glob("*NOTICE*"):
        shutil.copyfile(extra, prov / extra.name)
    methods = output / "methods"
    methods.mkdir()
    cases = {}
    for case in corpus["population"]:
        name = case["id"]
        if slices_mode:
            raw = (input_dir / (name + ".java")).read_bytes()
            require(sha(raw) == stated[name]["sha256"], "connector slice hash: " + name)
            text, offsets = extract_method(raw.decode("utf-8"), case["method"], case["parameters"])
            require(text.encode() == raw, "slice must contain only the exact selected declaration")
            provenance[name] = {**corpus["sources"][case["source"]], **stated[name],
                                "git_blob_verified_locally": False, "mode": "reviewed_connector_excerpt"}
        else:
            text, offsets = extract_method(originals[case["source"]], case["method"], case["parameters"])
            provenance[name] = {"source": case["source"], **offsets, "sha256": sha(text.encode())}
        slices[name] = text
        method_path = methods / (name + ".java")
        method_path.write_bytes(text.encode())
        tried = {p: probe(p, method_path, corpus["budget"]["per_profile_timeout_seconds"]) for p in corpus["profiles"]}
        cases[name] = {"source_sha256": sha(text.encode()), "source_attempts": tried,
                       "target_status": "not_run_no_independent_goal_bridge", "new_qkf_certificate": None}
    for name, source in originals.items():
        (prov / (name + ".java")).write_bytes(source.encode())
    if not slices_mode:
        require("public static final long MIN_VALUE = 0x8000000000000000L;" in originals["jdk_long"],
                "exact original JDK wrapper constant")
        code = lexical_code(originals["lucene_bits"])
        for declaration in CONSTANTS.splitlines():
            require(declaration.strip() in code, "exact original Lucene wrapper constant")
    save(prov / "IDENTITIES.json", provenance)
    attempts = [v["outcome"]["status"] for c in cases.values() for v in c["source_attempts"].values()]
    native = native_run(corpus, slices, output)
    calibration = calibrate(input_dir, output, corpus)
    summary = {"schema": "qkf-external-applicability-result-v1", "engine_commit": corpus["engine_commit"],
               "acquisition": "provisional_connector_slices" if slices_mode else "full_original_blobs",
               "frozen_protocol_complete": (not slices_mode and native["status"] == "matched"
                   and all(c["status"] == "certified" for c in calibration.values())
                   and all(s in {"source_parsed", "source_unsupported"} for s in attempts)),
               "source_methods": len(cases), "source_profile_attempts": len(attempts),
               "source_attempt_counts": dict(Counter(attempts)),
               "source_parsed_methods": sum(any(a["outcome"]["status"] == "source_parsed"
                   for a in c["source_attempts"].values()) for c in cases.values()),
               "new_target_proofs": 0, "new_program_refutations": 0, "cases": cases,
               "native": native, "calibration": calibration, "python": sys.version,
               "protocol_files": {f: sha((HERE / f).read_bytes()) for f in ("CORPUS.json", "ENGINE.json", "PROTOCOL.md")}}
    save(output / "SUMMARY.json", summary)
    semantic = {"source_attempt_counts": summary["source_attempt_counts"],
                "cases": {k: {"source_sha256": c["source_sha256"], "source_attempts":
                    {p: a["outcome"] for p, a in c["source_attempts"].items()}, "target_status": c["target_status"]}
                    for k, c in cases.items()},
                "native": native.get("cases"), "calibration": calibration}
    save(output / "SEMANTIC.json", semantic)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--connector-slices", action="store_true", help="Provisional only: full-blob acceptance remains unperformed")
    args = parser.parse_args()
    result = execute(args.inputs.resolve(), args.output.resolve(), slices_mode=args.connector_slices)
    print(json.dumps({k: v for k, v in result.items() if k not in ("cases", "native")}, indent=2))
    return 0 if result["native"]["status"] == "matched" and all(c["status"] == "certified" for c in result["calibration"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
