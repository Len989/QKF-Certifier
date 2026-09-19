"""Independent finite/native validation for the Graal create joint carrier."""

from collections import Counter
from pathlib import Path
import os
import random
import shutil
import subprocess
import tempfile

from .create_math import (
    SUPPORTED_BITS,
    equivalent_result,
    exact_extrema,
    execute_create,
    max_value,
    min_value,
    signed_word,
    unsigned_word,
    word_mask,
)
from research.observations.model import require

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "research/graal/native/IntegerStamp.java"


def _legal(values, x):
    u = unsigned_word(x, values["bits"])
    return (
        values["lower"] <= x <= values["upper"]
        and u & values["must"] == values["must"]
        and not (u & ~values["may"] & word_mask(values["bits"]))
        and (values["can_zero"] or x != 0)
    )


def exhaustive_small(max_bits=4):
    require(type(max_bits) is int and 1 <= max_bits <= 5, "small-width validation budget")
    counts = Counter()
    iterations = Counter()
    total = 0

    for bits in range(1, max_bits + 1):
        values = range(min_value(bits), max_value(bits) + 1)
        masks = range(1 << bits)
        for lower in values:
            for upper in values:
                for must in masks:
                    for may in masks:
                        for can_zero in (False, True):
                            item = {
                                "bits": bits, "lower": lower, "upper": upper,
                                "must": must, "may": may, "can_zero": can_zero,
                            }
                            result = execute_create(item)
                            actual = [
                                x for x in range(min_value(bits), max_value(bits) + 1)
                                if _legal(item, x)
                            ]
                            if not actual:
                                require(result["kind"] == "empty",
                                        "small create model missed exact emptiness")
                                counts["empty"] += 1
                            else:
                                require(result["kind"] == "value",
                                        "small create model invented emptiness")
                                require(result["lower"] == min(actual)
                                        and result["upper"] == max(actual),
                                        "small create extrema")
                                normalized = {
                                    **item,
                                    "lower": result["lower"], "upper": result["upper"],
                                    "must": result["must"], "may": result["may"],
                                    "can_zero": result["zero_member"],
                                }
                                following = [
                                    x for x in range(min_value(bits), max_value(bits) + 1)
                                    if _legal(normalized, x)
                                ]
                                require(following == actual,
                                        "small create normalization preserves exact set")
                                counts["value"] += 1
                            require(result["iterations"] <= 3, "source iteration limit")
                            iterations[result["iterations"]] += 1
                            total += 1

    return {
        "inputs": total,
        "widths": [1, max_bits],
        "outcomes": dict(counts),
        "iterations": dict(iterations),
        "mismatches": 0,
    }


def _random_input(rng, bits):
    return {
        "bits": bits,
        "lower": signed_word(rng.getrandbits(bits), bits),
        "upper": signed_word(rng.getrandbits(bits), bits),
        "must": rng.getrandbits(bits),
        "may": rng.getrandbits(bits),
        "can_zero": bool(rng.getrandbits(1)),
    }


def physical_dp(samples_per_width=300):
    require(type(samples_per_width) is int and 1 <= samples_per_width <= 5000,
            "physical DP validation budget")
    rng = random.Random(1909202601)
    cases = []
    for bits in SUPPORTED_BITS:
        cases.extend(_random_input(rng, bits) for _ in range(samples_per_width))

    cases.extend([
        {"bits": 1, "lower": -1, "upper": 0, "must": 0, "may": 1, "can_zero": False},
        {"bits": 8, "lower": -128, "upper": 127, "must": 0, "may": 255, "can_zero": True},
        {"bits": 8, "lower": -1, "upper": 1, "must": 0, "may": 255, "can_zero": False},
        {"bits": 8, "lower": -128, "upper": -126, "must": 1, "may": 0x83, "can_zero": False},
        {"bits": 32, "lower": 0, "upper": 0, "must": 0, "may": 0, "can_zero": False},
        {"bits": 64, "lower": -(1 << 63), "upper": (1 << 63) - 1,
         "must": 0, "may": (1 << 64) - 1, "can_zero": True},
        {"bits": 64, "lower": -7, "upper": 7,
         "must": 1 << 63, "may": (1 << 64) - 1, "can_zero": False},
    ])

    counts = Counter()
    iteration_counts = Counter()
    stable_three = 0
    for item in cases:
        result = execute_create(item)
        require(equivalent_result(item, result), "independent DP create denotation")
        lo, hi = exact_extrema(item)
        if lo is None:
            require(result["kind"] == "empty", "DP exact empty")
            counts["empty"] += 1
        else:
            require(result["kind"] == "value"
                    and result["lower"] == lo and result["upper"] == hi,
                    "DP exact extrema")
            counts["value"] += 1
        require(result["iterations"] <= 3, "DP source iteration limit")
        iteration_counts[result["iterations"]] += 1
        stable_three += result["kind"] == "value" and result["iterations"] == 3

    return {
        "inputs": len(cases),
        "supported_bits": list(SUPPORTED_BITS),
        "outcomes": dict(counts),
        "iterations": dict(iteration_counts),
        "three_iteration_examples": stable_three,
        "mismatches": 0,
    }, cases


HARNESS = r"""
import java.io.*;
public class CreateJointHarness {
    public static void main(String[] args) throws Exception {
        var input = new BufferedReader(new InputStreamReader(System.in));
        String line;
        while ((line = input.readLine()) != null) {
            String[] p = line.split(" ");
            int bits = Integer.parseInt(p[0]);
            long lower = Long.parseLong(p[1]);
            long upper = Long.parseLong(p[2]);
            long must = Long.parseLong(p[3]);
            long may = Long.parseLong(p[4]);
            boolean canZero = Boolean.parseBoolean(p[5]);
            IntegerStamp s = IntegerStamp.create(bits, lower, upper, must, may, canZero);
            if (!s.hasValues()) {
                System.out.println("empty");
            } else {
                System.out.println("value " + s.lowerBound() + " " + s.upperBound() + " "
                        + s.mustBeSet() + " " + s.mayBeSet() + " " + s.contains(0));
            }
        }
    }
}
"""


def _java_mask_value(value, bits):
    value &= word_mask(bits)
    if bits == 64 and value >= 1 << 63:
        return value - (1 << 64)
    return value


def native_fixture(cases):
    java, javac = shutil.which("java"), shutil.which("javac")
    require(java is not None and javac is not None, "JDK required for create native validation")
    require(FIXTURE.is_file(), "retained compiled Graal fixture")

    selected = [x for x in cases if x["bits"] in SUPPORTED_BITS]
    payload = "".join(
        f'{x["bits"]} {x["lower"]} {x["upper"]} '
        f'{_java_mask_value(x["must"], x["bits"])} '
        f'{_java_mask_value(x["may"], x["bits"])} '
        f'{str(x["can_zero"]).lower()}\n'
        for x in selected
    )

    env = os.environ.copy()
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        fixture = root / "IntegerStamp.java"
        fixture.write_bytes(FIXTURE.read_bytes())
        harness = root / "CreateJointHarness.java"
        harness.write_text(HARNESS, encoding="utf-8")
        compilation = subprocess.run(
            [javac, str(fixture), str(harness)],
            text=True, capture_output=True, cwd=root, env=env, timeout=90,
        )
        require(compilation.returncode == 0,
                "create native compilation: " + compilation.stderr[-4000:])
        execution = subprocess.run(
            [java, "-ea", "-cp", temp, "CreateJointHarness"],
            input=payload, text=True, capture_output=True, cwd=root, env=env, timeout=90,
        )
        require(execution.returncode == 0,
                "create native execution: " + execution.stderr[-4000:])

    lines = execution.stdout.splitlines()
    require(len(lines) == len(selected), "one native create answer per input")
    for item, line in zip(selected, lines):
        expected = execute_create(item)
        if line == "empty":
            actual = {"kind": "empty"}
        else:
            p = line.split()
            require(len(p) == 6 and p[0] == "value", "native create output format")
            actual = {
                "kind": "value",
                "lower": int(p[1]),
                "upper": int(p[2]),
                "must": int(p[3]) & word_mask(item["bits"]),
                "may": int(p[4]) & word_mask(item["bits"]),
                "zero_member": p[5] == "true",
            }
        require(actual["kind"] == expected["kind"], "native create empty/value agreement")
        if actual["kind"] == "value":
            for key in ("lower", "upper", "must", "may", "zero_member"):
                require(actual[key] == expected[key], "native create field: " + key)

    return {
        "inputs": len(selected),
        "supported_bits": list(SUPPORTED_BITS),
        "mismatches": 0,
        "fixture": "research/graal/native/IntegerStamp.java",
    }


def validate(*, native=False, small_bits=4, samples_per_width=300):
    small = exhaustive_small(small_bits)
    physical, cases = physical_dp(samples_per_width)
    result = {
        "schema": "qkf-graal-create-validation-v1",
        "small_exhaustive": small,
        "physical_digit_dp": physical,
        "native": native_fixture(cases) if native else {"status": "not_run"},
        "scope": (
            "implementation validation for the source-bound create model; "
            "the universal certificate additionally relies on the declared fixed caller rules"
        ),
    }
    return result
