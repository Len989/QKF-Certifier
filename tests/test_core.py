import copy
import itertools
import json
from pathlib import Path

import pytest
from word_oracle import evaluate, exact_output, expr_value, kbwords

from qkf_certifier import InvalidCertificate, check_certificate, inspect, normalize, verify
from qkf_certifier.certificate import loads
from qkf_certifier.frontend import parse_bundle
from qkf_certifier.kernel import frozen


@pytest.mark.parametrize("name", ["and", "or", "xor"])
def test_real_sources_against_concrete_values(bundle, name):
    sources = bundle(name)
    r = verify(sources, name)
    assert r["status"] == "certified" and r["optimal"] and r["all_positive_widths"]
    c = r["certificate"]
    assert check_certificate(sources, name, loads(json.dumps(c)))["status"] == "certified"
    f = parse_bundle(sources)
    nf = frozen(c["normal_form"])
    for w in range(1, 5):
        for a, b in itertools.product(kbwords(w), repeat=2):
            assert evaluate(f, (a, b), w) == expr_value(nf, a + b, w) == exact_output(a, b, w, name)


@pytest.mark.parametrize(
    "field",
    [
        "schema",
        "sources",
        "entry",
        "semantics",
        "initial_hash",
        "steps",
        "normal_form",
        "target",
        "rows",
    ],
)
def test_certificate_field_types(bundle, field):
    b = bundle("xor")
    c = verify(b, "xor")["certificate"]
    c[field] = None
    with pytest.raises(InvalidCertificate):
        check_certificate(b, "xor", c)


@pytest.mark.parametrize(
    "attack",
    [
        "bool_as_int",
        "float_as_int",
        "row_bool_as_int",
        "extra_field",
        "unknown_rule",
        "wrong_path",
        "missing_step",
        "wrong_target",
        "stale_source",
        "stale_helper",
        "forged_helper_hash",
    ],
)
def test_tampering(bundle, attack):
    b = bundle("xor")
    c = copy.deepcopy(verify(b, "xor")["certificate"])
    if attack == "bool_as_int":
        c["normal_form"] = ["pair", ["var", True], ["zero"]]
    elif attack == "float_as_int":
        c["normal_form"] = ["pair", ["var", 1.0], ["zero"]]
    elif attack == "row_bool_as_int":
        c["rows"][0]["out"][0] = True
    elif attack == "extra_field":
        c["proved_by_magic"] = True
    elif attack == "unknown_rule":
        c["steps"][0]["rule"] = "assume_true"
    elif attack == "wrong_path":
        c["steps"][0]["path"] = [False]
    elif attack == "missing_step":
        c["steps"] = c["steps"][1:]
    elif attack == "wrong_target":
        c["target"] = "and"
    elif attack == "stale_source":
        b["program"] += "\n"
    else:
        b["meet"] = b["meet"].replace('"transfer.or"', '"transfer.and"')
        if attack == "forged_helper_hash":
            import hashlib

            c["sources"]["meet"] = hashlib.sha256(b["meet"].encode()).hexdigest()
    with pytest.raises(InvalidCertificate):
        check_certificate(b, "xor", c)


@pytest.mark.parametrize("text", ["{}", "[]", "null", '{"schema":NaN}', '{"x":1,"x":2}'])
def test_bad_json(text):
    with pytest.raises(InvalidCertificate):
        loads(text)


def test_actual_return_and_witness(bundle):
    b = bundle("and")
    b["program"] = b["program"].replace("func.return %10", "func.return %arg0")
    r = verify(b, "and")
    assert r["status"] == "unsound" and not r["all_positive_widths"]
    witness = r["witness"]
    assert witness["x"] & witness["y"] == witness["concrete_result"]
    assert check_certificate(b, "and", r["certificate"])["status"] == "unsound"


def test_helper_semantics_checked_not_assumed(bundle):
    b = bundle("xor")
    b["meet"] = b["meet"].replace('"transfer.or"', '"transfer.and"')
    r = verify(b, "xor")
    assert r["status"] == "certified" and not r["optimal"]


def test_coordinate_signature(bundle):
    r = inspect(bundle("xor"))
    assert r["status"] == "normalized"
    assert r["semantic_signature"] == "00189" and r["coordinatewise"]
    assert not r["all_positive_widths"]


def test_normalization_only_is_not_soundness(bundle):
    b = bundle("xor")
    r = normalize(b)
    assert r["status"] == "normalized"
    c = r["certificate"]
    assert c["target"] is None and "rows" not in c
    with pytest.raises(InvalidCertificate):
        check_certificate(b, "xor", c)
    assert check_certificate(b, None, c)["normalization_verified"]


def test_checker_does_not_run_search(bundle, monkeypatch):
    b = bundle("xor")
    c = verify(b, "xor")["certificate"]
    import qkf_certifier.producer as producer

    def fail(*args, **kwargs):
        raise AssertionError("checker called search")

    monkeypatch.setattr(producer, "normalize", fail)
    assert check_certificate(b, "xor", c)["status"] == "certified"


def test_serialization_is_deterministic(bundle):
    b = bundle("xor")
    assert json.dumps(verify(b, "xor")["certificate"]) == json.dumps(
        verify(dict(reversed(list(b.items()))), "xor")["certificate"]
    )


def test_json_schema_matches_emitted_certificates(bundle):
    import jsonschema

    schema = json.loads(
        (Path(__file__).resolve().parents[1] / "docs/certificate.schema.json").read_text()
    )
    for name in ("and", "or", "xor"):
        jsonschema.validate(verify(bundle(name), name)["certificate"], schema)
        jsonschema.validate(normalize(bundle(name))["certificate"], schema)
