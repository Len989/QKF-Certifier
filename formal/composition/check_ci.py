"""Clean pinned Lean build, exact axiom audit and independent integrity controls."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path

from .export import render
from .fixtures import ROOT, regenerate
from .preserve import audit

REPO = ROOT.parents[1]
THEOREMS = [
    "select_sound",
    "residual_sound",
    "derive_sound",
    "entry_sound",
    "replay_sound",
    "consumer_sound",
    "conservative_extension",
    "check_replay",
    "all_admitted_sound",
    "check_sound",
    "accepted_consumer_typed",
    "accepted_consumer_values",
]


def source_files():
    return {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(ROOT.rglob("*"))
        if p.is_file() and not {".lake", "__pycache__"}.intersection(p.relative_to(ROOT).parts)
    }


def run(output, lake="lake", require_clean=False):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    before, preserved = source_files(), audit()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO, text=True)
    if require_clean and dirty:
        raise ValueError("CI requires a clean tested commit")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=REPO, text=True).strip()
    commands = []

    def command(label, args, cwd=ROOT, success=True):
        process = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=600)
        text = process.stdout + process.stderr
        (output / (label + ".log")).write_text(text)
        commands.append(
            dict(label=label, args=args, returncode=process.returncode, expected_success=success)
        )
        if (process.returncode == 0) != success:
            raise ValueError(label + " unexpected result: " + text[-3000:])
        return text

    try:
        version = command("version", [lake, "env", "lean", "--version"])
        if not re.search(r"Lean \(version 4\.33\.0,", version):
            raise ValueError("wrong Lean toolchain")
        fixture = regenerate(check_only=True)
        command("clean", [lake, "clean"])
        command("clean-ground", [lake, "clean"], cwd=ROOT.parent / "ground")
        command("build", [lake, "build"])
        names = ["QKFComposition." + name for name in THEOREMS]
        names += [
            "QKFComposition.Examples." + c["name"] + ("_accepted" if c["expected"] else "_rejected")
            for c in fixture["cases"]
        ]
        audit_file = output / "Axioms.lean"
        audit_file.write_text(
            "import Composition\nimport CompositionExamples\n"
            + "\n".join("#print axioms " + name for name in names)
            + "\n"
        )
        text = command("axioms", [lake, "env", "lean", str(audit_file)])
        axioms = {}
        for line in text.splitlines():
            m = re.fullmatch(r"'([^']+)' depends on axioms: \[(.*)\]", line)
            if m:
                axioms[m[1]] = m[2].split(", ") if m[2] else []
            m = re.fullmatch(r"'([^']+)' does not depend on any axioms", line)
            if m:
                axioms[m[1]] = []
        if set(axioms) != set(names) or any(
            set(a) - {"propext", "Quot.sound"} for a in axioms.values()
        ):
            raise ValueError("unexpected or incomplete axiom dependencies")
        # Independently reject a falsely asserted positive theorem, even if a
        # hostile exporter changes the intended expected result to `true`.
        bad = json.loads((ROOT / "evidence/reject_self_support.decoded.json").read_text())
        forged = output / "ForgedExport.lean"
        forged.write_text(
            "import Composition\nopen QKFGround\n" + render("forged", bad, accepted=True)
        )
        log = command("forged-export-rejected", [lake, "env", "lean", str(forged)], success=False)
        if "decide" not in log or "error:" not in log:
            raise ValueError("forged export failed for an unrelated reason")
        for label, declaration in (
            ("proof-hole", "theorem unsupported : False := by sorry"),
            ("new-axiom", "axiom unproved : False\ntheorem unsupported : False := unproved"),
        ):
            control = output / (label + ".lean")
            control.write_text(
                "import Composition\n"
                + declaration
                + "\n"
                + "/-- info: 'unsupported' does not depend on any axioms -/\n"
                + "#guard_msgs in\n#print axioms unsupported\n"
            )
            log = command(label + "-rejected", [lake, "env", "lean", str(control)], success=False)
            if "guard_msgs" not in log:
                raise ValueError("axiom control failed for an unrelated reason")
        for optimized in (False, True):
            command(
                "python-optimized" if optimized else "python-normal",
                [sys.executable]
                + (["-O"] if optimized else [])
                + ["-m", "unittest", "formal.composition.test_export"],
                cwd=REPO,
            )
        if before != source_files() or preserved != audit():
            raise ValueError("source changed during formal validation")
        count = unittest.defaultTestLoader.loadTestsFromName(
            "formal.composition.test_export"
        ).countTestCases()
        positives = [c for c in fixture["cases"] if c["expected"]]
        result = dict(
            schema="qkf-composition-lean-validation-v1",
            status="passed",
            lean_version=version.strip(),
            revision=revision,
            tree=tree,
            source_dirty=bool(dirty),
            source_sha256=before,
            preservation=preserved,
            positive_packets=fixture["positive_count"],
            negative_packets=fixture["negative_count"],
            consumers=sum(c["consumers"] for c in positives),
            derived_via_links=sum(c["via_links"] for c in positives),
            general_theorems_audited=len(THEOREMS),
            axioms=axioms,
            integrity_controls=["forged-export", "proof-hole", "new-axiom"],
            python_tests=count,
            python_modes=["normal", "-O"],
            commands=commands,
            scope="F1b: decoded typed composition under explicit native assumptions; source and runtime semantics excluded",
        )
        with zipfile.ZipFile(output / "checked_project.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            for name in before:
                archive.write(ROOT / name, name)
        (output / "RESULT.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        return result
    except Exception as error:
        (output / "FAILURE.json").write_text(
            json.dumps(dict(error=str(error), commands=commands), indent=2)
        )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--lake", default="lake")
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args()
    result = run(args.output, args.lake, args.require_clean)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "status",
                    "positive_packets",
                    "negative_packets",
                    "consumers",
                    "general_theorems_audited",
                    "python_tests",
                )
            },
            sort_keys=True,
        )
    )
