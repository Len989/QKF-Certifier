"""Kernel/compiler validation for the Graal-create caller invariant slice.

Acceptance requires a fresh Lean 4.33.0 build, a strict theorem/axiom audit,
two-sided semantic controls, an isolated placeholder rejection, and replay of
the accepted PR19 source/rule binding. This driver is evidence plumbing, not a
replacement for the Lean proofs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.lean_targets.check_ci import (  # noqa: E402
    PROJECT,
    check_source_bindings,
    require,
    run_command,
)
from research.create_joint.create_kernel import DERIVATION  # noqa: E402
from research.create_joint.create_source import FIXTURE, read_source  # noqa: E402

THEOREMS = (
    "QKFTarget.Create.signed_order_low",
    "QKFTarget.Create.signed_order_high",
    "QKFTarget.Create.signed_order_same_bucket",
    "QKFTarget.Create.interval_key_eq",
    "QKFTarget.Create.common_prefix_refinement_preserves",
    "QKFTarget.Create.exact_extrema_tighten",
    "QKFTarget.Create.exact_empty_iff_no_legal",
    "QKFTarget.Create.greater_witness_from_maximum",
    "QKFTarget.Create.third_pass_confirmation",
    "QKFTarget.Create.exact_ceiling_from_caller_contracts",
)
CONTROLS = (
    "mixedBucketOrderAgrees",
    "commonPrefixBroken",
    "thirdPassWithoutNormality",
)
ALLOWED_AXIOMS = {"propext", "Quot.sound"}
REQUIRED_CALLER_RULES = {
    "prefix_refinement",
    "signed_bucket_bridge",
    "post_helper_empty",
    "two_update_stabilization",
    "monotonic_guarantees",
}


def audit_output(text):
    records = {}
    for name in THEOREMS:
        pattern = (
            "'" + re.escape(name)
            + "' (?:does not depend on any axioms|depends on axioms: \\[([^\\]]*)\\])"
        )
        matches = list(re.finditer(pattern, text))
        require(len(matches) == 1, "missing or repeated create audit: " + name)
        raw = matches[0].group(1)
        axioms = [] if raw is None else [x.strip() for x in raw.split(",") if x.strip()]
        require(set(axioms) <= ALLOWED_AXIOMS, "unexpected create axioms: " + name)
        records[name] = axioms
    return records


def proof_rejected(info):
    text = (info["stdout"] + info["stderr"]).lower()
    return (
        info["status"] == "failed"
        and "decide" in text
        and "false" in text
        and not any(
            marker in text
            for marker in (
                "unknown identifier",
                "unknown constant",
                "unexpected token",
                "file not found",
                "unknown module",
                "maximum recursion",
                "maximum number of steps",
                "failed to synthesize",
            )
        )
    )


def control_text(name, expected):
    require(name in CONTROLS or name == "positiveExamples", "known create semantic control")
    require(type(expected) is bool, "Boolean create control expectation")
    return (
        "import QKFTarget.CreateControls\n"
        "example : QKFTarget.Create.Controls."
        + name
        + " = "
        + ("true" if expected else "false")
        + " := by decide\n"
    )


def caller_bridge():
    source = FIXTURE.read_text(encoding="utf-8")
    binding = read_source(source)
    rules = {row[0] for row in DERIVATION}
    require(REQUIRED_CALLER_RULES <= rules, "PR19 caller rule population changed")
    return {
        "fixture_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "source_binding_sha256": hashlib.sha256(
            json.dumps(binding, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "required_rules": sorted(REQUIRED_CALLER_RULES),
        "all_required_rules_present": True,
        "source_contract_schema": binding["schema"],
    }


def validate(output, *, timeout=300):
    require(type(timeout) is int and 1 <= timeout <= 900, "budget 1..900 seconds")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    result = {
        "schema": "qkf-create-lean-validation-v1",
        "status": "not_checked",
        "lean_checked": False,
        "required_version": "4.33.0",
        "time_budget_seconds": timeout,
        "commands": [],
        "controls": [],
        "source_parser_verified_by_lean": False,
        "python_caller_rules_fully_eliminated": False,
        "scope": (
            "kernel-checked signed-bucket/common-prefix/extrema/empty/final-confirmation "
            "lemmas plus handoff to existing exact ceiling; source-to-premise mapping remains external"
        ),
    }

    def finish(status, **details):
        result.update(
            status=status,
            **details,
            elapsed_seconds=round(time.monotonic() - started, 6),
        )
        (output / "RESULT.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return result

    def command(name, argv, cwd):
        info = run_command(argv, cwd, timeout - (time.monotonic() - started))
        for stream in ("stdout", "stderr"):
            (output / (name + "." + stream + ".log")).write_text(
                info[stream], encoding="utf-8"
            )
        result["commands"].append(
            {
                "name": name,
                "argv": argv,
                **{k: v for k, v in info.items() if k not in ("stdout", "stderr")},
            }
        )
        print(json.dumps({"command": name, "status": info["status"]}), flush=True)
        return info

    try:
        result["existing_source_binding"] = check_source_bindings()
        result["create_caller_bridge"] = caller_bridge()

        sources = {
            p.relative_to(PROJECT).as_posix(): p.read_bytes()
            for p in sorted(PROJECT.rglob("*.lean"))
            if ".lake" not in p.parts
        }
        result["lean_source_sha256"] = {
            name: hashlib.sha256(raw).hexdigest() for name, raw in sources.items()
        }
        for name, raw in sources.items():
            require(
                not re.search(
                    r"\b(?:sorry|admit|native_decide|bv_decide)\b|^\s*(?:axiom|unsafe)\b",
                    raw.decode("utf-8"),
                    re.MULTILINE,
                ),
                "proof shortcut in " + name,
            )

        lean, lake = shutil.which("lean"), shutil.which("lake")
        if not lean or not lake:
            return finish("unavailable", reason="Lean/lake executable not installed")

        version = command("version", [lean, "--version"], PROJECT)
        if version["status"] != "success":
            return finish(version["status"], stage="version")
        if not re.search(r"\bversion 4\.33\.0\b", version["stdout"]):
            return finish("wrong_toolchain")
        result["lean_version"] = version["stdout"].strip()

        with tempfile.TemporaryDirectory(prefix="qkf-create-lean-") as temporary:
            fresh = Path(temporary) / "project"
            shutil.copytree(
                PROJECT,
                fresh,
                ignore=shutil.ignore_patterns(".lake", "__pycache__", "validation"),
            )
            built = command(
                "fresh_build", [lake, "build", "QKFTarget.CreateControls"], fresh
            )
            if built["status"] != "success":
                return finish(built["status"], stage="fresh_build")

            audit = command("axioms", [lake, "env", "lean", "CreateAudit.lean"], fresh)
            if audit["status"] != "success":
                return finish(audit["status"], stage="audit")
            result["axioms"] = audit_output(audit["stdout"])

            probe = fresh / "Probe.lean"
            probe.write_text(control_text("positiveExamples", True), encoding="utf-8")
            positive = command(
                "positive_examples", [lake, "env", "lean", "Probe.lean"], fresh
            )
            if positive["status"] != "success":
                return finish("positive_control_failed")

            for name in CONTROLS:
                probe.write_text(control_text(name, False), encoding="utf-8")
                false = command(
                    name + "_is_false", [lake, "env", "lean", "Probe.lean"], fresh
                )
                if false["status"] != "success":
                    return finish("negative_control_invalid", stage=name)

                probe.write_text(control_text(name, True), encoding="utf-8")
                wrong = command(
                    name + "_cannot_be_true", [lake, "env", "lean", "Probe.lean"], fresh
                )
                rejected = proof_rejected(wrong)
                result["controls"].append(
                    {
                        "case": name,
                        "false_proved": True,
                        "false_claim_rejected": rejected,
                    }
                )
                if not rejected:
                    return finish("negative_control_failed", stage=name)

            target = fresh / "QKFTarget/Create.lean"
            text = target.read_text(encoding="utf-8")
            begin = text.index("theorem third_pass_confirmation ")
            end = text.index(
                "\n/-- Existing exact-ceiling composition consumes", begin
            )
            declaration = text[begin:end].split(":= by", 1)[0]
            target.write_text(
                text[:begin] + declaration + ":= by sorry\n" + text[end:],
                encoding="utf-8",
            )
            placeholder = command(
                "placeholder_build", [lake, "build", "QKFTarget.CreateControls"], fresh
            )
            if placeholder["status"] != "success":
                return finish("placeholder_control_invalid", stage="build")
            bad_audit = command(
                "placeholder_axioms", [lake, "env", "lean", "CreateAudit.lean"], fresh
            )
            require(
                bad_audit["status"] == "success" and "sorryAx" in bad_audit["stdout"],
                "placeholder must reach the real create axiom audit",
            )
            try:
                audit_output(bad_audit["stdout"])
            except ValueError:
                result["placeholder_rejected_by_audit"] = True
            else:
                return finish("placeholder_control_failed")

        for name, raw in sources.items():
            destination = output / "checked_sources" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)

        return finish("accepted", lean_checked=True)
    except (ValueError, TypeError, KeyError, OSError, IndexError) as exc:
        return finish("rejected", error=str(exc))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    try:
        result = validate(args.output, timeout=args.timeout)
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "input_error", "error": str(exc)}))
        return 3
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "accepted" and result["lean_checked"] is True else 3


if __name__ == "__main__":
    raise SystemExit(main())
