"""Source-only guarded coverage CLI; target proofs use research.unified.v6."""
import argparse
import json
from pathlib import Path
from research.observations.model import require
from research.signed_bridge.model import request
from research.unified.run import load_json, save_json
from research.wordexpr.frontend import Unsupported
from .checker import check_observations, explain


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument("command", choices=("infer", "check", "explain"))
    p.add_argument("source", type=Path)
    p.add_argument("--class", dest="class_name", required=True)
    p.add_argument("--method", required=True)
    p.add_argument("--word-type", choices=("int", "long"), required=True)
    p.add_argument("--certificate", type=Path, required=True)
    p.add_argument("--budget", type=Path)
    a = p.parse_args(argv)
    try:
        require(a.command == "infer" or a.budget is None, "budget is a discovery input")
        raw = a.source.read_bytes(); require(len(raw) <= 2_000_000, "source byte ceiling")
        text = raw.decode("utf-8")
        selection = request({"class": a.class_name, "method": a.method}, a.word_type)
        if a.command == "infer":
            require(not a.certificate.exists(), "new certificate path required")
            from .producer import infer
            opts = {} if a.budget is None else load_json(a.budget)
            require(type(opts) is dict and set(opts) <= {"max_states", "max_steps", "max_local_steps",
                    "max_observations", "max_pullbacks", "max_classes"}, "source-only budget fields")
            cert, out = infer(text, selection, **opts)
            if cert is not None: save_json(a.certificate, cert)
        else:
            try:
                cert = load_json(a.certificate)
                out = explain(text, selection, cert) if a.command == "explain" else check_observations(text, selection, cert)
            except (ValueError, TypeError, KeyError, IndexError, RecursionError) as exc:
                out = {"status": "invalid_certificate", "error": str(exc)}
    except Unsupported as exc:
        out = {"status": "unsupported", "error": str(exc)}
    except (ValueError, TypeError, KeyError, IndexError, OSError, UnicodeError, RecursionError) as exc:
        out = {"status": "input_error", "error": str(exc)}
    print(json.dumps(out, ensure_ascii=False, sort_keys=True, allow_nan=False))
    status = out.get("status", out.get("result", {}).get("status"))
    return {"source_observation_verified": 0, "unsupported": 2, "budget_exhausted": 2,
            "invalid_certificate": 3, "input_error": 64}.get(status, 70)


if __name__ == "__main__": raise SystemExit(main())
