"""Command line adapter: no network access or subprocesses during verification."""

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from . import __version__
from .api import check_certificate, inspect, normalize, verify
from .certificate import _no_duplicates, loads
from .errors import InvalidCertificate, InvalidInput, ResourceLimit, Unsupported
from .limits import MAX_BATCH_ITEMS, MAX_CERTIFICATE_BYTES, MAX_SOURCE_BYTES

CODES = {
    "certified": 0,
    "normalized": 0,
    "unsound": 1,
    "fallback_required": 2,
    "invalid_certificate": 3,
    "input_error": 64,
    "internal_error": 70,
}


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise InvalidInput(message)


def read_text(path, limit):
    with Path(path).open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ResourceLimit(f"file exceeds {limit} bytes: {path}")
    return data.decode("utf-8")


def sources_from(source, helpers):
    bundle = {"program": read_text(source, MAX_SOURCE_BYTES)}
    paths = [Path(source).resolve()]
    for helper in helpers:
        name, sep, path = helper.partition("=")
        if not sep or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", name) or name in bundle:
            raise InvalidInput("helpers must be unique NAME=PATH pairs; program is reserved")
        bundle[name] = read_text(path, MAX_SOURCE_BYTES)
        paths.append(Path(path).resolve())
    return bundle, paths


def write_json(path, value, force, inputs):
    destination = Path(path).resolve()
    if destination in inputs:
        raise InvalidInput("output must not replace an input file")
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=destination.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if force:
            os.replace(temporary, destination)
        else:
            os.link(temporary, destination)
    except FileExistsError as exc:
        raise InvalidInput(f"output exists (use --force to replace): {destination}") from exc
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def parser():
    p = ArgumentParser(
        prog="qkf", description="Check source-bound, width-independent KnownBits certificates."
    )
    p.add_argument("--version", action="version", version="QKF Certifier " + __version__)
    commands = p.add_subparsers(dest="command", required=True)
    for name, help_text in [
        ("verify", "Prove or refute a supported target"),
        ("check", "Replay a supplied certificate"),
        ("normalize", "Prove normalization only"),
        ("inspect", "Describe a checked normal form"),
    ]:
        c = commands.add_parser(name, help=help_text)
        c.add_argument("source", type=Path)
        c.add_argument("--helper", action="append", default=[], metavar="NAME=PATH")
        c.add_argument("--entry", default="solution")
        c.add_argument("--json", action="store_true", help="Print a single JSON result to stdout")
        if name == "verify":
            c.add_argument("--target", required=True, help="and, or, xor")
        if name == "check":
            g = c.add_mutually_exclusive_group(required=True)
            g.add_argument("--target", help="Expected target: and, or, xor")
            g.add_argument("--normalization-only", action="store_true")
            c.add_argument("--certificate", type=Path, required=True)
        if name in ("verify", "normalize"):
            c.add_argument("--certificate", type=Path, help="Write generated certificate")
            c.add_argument("--force", action="store_true")
    b = commands.add_parser(
        "batch", help="Verify a source manifest without stopping at the first failure"
    )
    b.add_argument("manifest", type=Path)
    b.add_argument("--json", action="store_true")
    return p


def run_one(args):
    bundle, paths = sources_from(args.source, args.helper)
    if args.command == "check":
        certificate = loads(read_text(args.certificate, MAX_CERTIFICATE_BYTES))
        return check_certificate(
            bundle, None if args.normalization_only else args.target, certificate, args.entry
        )
    if args.command == "inspect":
        return inspect(bundle, args.entry)
    result = (
        verify(bundle, args.target, args.entry)
        if args.command == "verify"
        else normalize(bundle, args.entry)
    )
    cert = result.pop("certificate", None)
    result["certificate_written"] = False
    if cert is not None and args.certificate is not None:
        write_json(args.certificate, cert, args.force, paths)
        result["certificate_written"] = True
    return result


def batch(path):
    try:
        data = json.loads(read_text(path, MAX_SOURCE_BYTES), object_pairs_hook=_no_duplicates)
    except (json.JSONDecodeError, InvalidCertificate) as exc:
        raise InvalidInput("invalid batch JSON") from exc
    if (
        type(data) is not dict
        or set(data) != {"schema", "items"}
        or data["schema"] != "qkf-batch-v1"
        or type(data["items"]) is not list
    ):
        raise InvalidInput("expected qkf-batch-v1 with an items array")
    if not 0 < len(data["items"]) <= MAX_BATCH_ITEMS:
        raise InvalidInput("batch must contain 1..256 items")
    root = Path(path).resolve().parent
    results = []
    ids = set()
    for item in data["items"]:
        if (
            type(item) is not dict
            or not {"id", "source", "target"} <= item.keys()
            or set(item) - {"id", "source", "target", "helpers", "entry"}
        ):
            raise InvalidInput("invalid batch item fields")
        if (
            any(type(item[k]) is not str or not item[k] for k in ("id", "source", "target"))
            or item["id"] in ids
        ):
            raise InvalidInput("batch ids must be unique; source/target must be nonempty strings")
        ids.add(item["id"])
        helpers = item.get("helpers", {})
        if type(helpers) is not dict or any(
            type(k) is not str or type(v) is not str for k, v in helpers.items()
        ):
            raise InvalidInput("invalid batch helpers")
        entry = item.get("entry", "solution")
        if type(entry) is not str or not entry:
            raise InvalidInput("invalid batch entry")
        try:
            bundle, _ = sources_from(
                root / item["source"], [k + "=" + str(root / v) for k, v in helpers.items()]
            )
            result = verify(bundle, item["target"], entry)
            result.pop("certificate", None)
        except (OSError, UnicodeError, InvalidInput) as exc:
            result = dict(status="input_error", reason=str(exc))
        except Unsupported as exc:
            result = dict(status="fallback_required", reason=str(exc))
        results.append(dict(id=item["id"], **result))
    status = "certified"
    for candidate in ("input_error", "invalid_certificate", "unsound", "fallback_required"):
        if any(r["status"] == candidate for r in results):
            status = candidate
            break
    return dict(schema="qkf-batch-result-v1", status=status, items=results)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    try:
        args = parser().parse_args(argv)
        result = batch(args.manifest) if args.command == "batch" else run_one(args)
    except InvalidCertificate as exc:
        result = dict(status="invalid_certificate", reason=str(exc))
    except Unsupported as exc:
        result = dict(status="fallback_required", reason=str(exc))
    except (InvalidInput, OSError, UnicodeError) as exc:
        result = dict(status="input_error", reason=str(exc))
    except (RecursionError, MemoryError) as exc:
        result = dict(status="fallback_required", reason="resource limit: " + type(exc).__name__)
    except Exception as exc:
        result = dict(status="internal_error", reason=type(exc).__name__ + ": " + str(exc))
    if as_json:
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    elif "items" in result:
        for row in result["items"]:
            print(row["id"] + ": " + row["status"])
    else:
        print(result["status"])
        if result.get("reason"):
            print(result["reason"])
        if result.get("all_positive_widths"):
            print(
                "All positive widths under the declared transfer semantics; optimal="
                + str(result["optimal"]).lower()
            )
        if result.get("witness"):
            print("Counterexample: " + json.dumps(result["witness"]))
        if result["status"] == "normalized":
            print("Normalization proved; target soundness has not been established.")
    return CODES.get(result["status"], 70)
