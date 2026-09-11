import itertools

import pytest
from mutation_helpers import variants
from word_oracle import evaluate, exact_output, expr_value, kbwords, sound_output

from qkf_certifier import check_certificate, normalize, verify
from qkf_certifier.frontend import parse_bundle
from qkf_certifier.kernel import frozen


@pytest.mark.parametrize("name,count", [("and", 85), ("xor", 239), ("or", 356)])
def test_real_program_mutations(bundle, name, count):
    original = bundle(name)
    mutants = variants(original["program"])
    assert len(mutants) == count
    cases = {
        w: [(a, b, exact_output(a, b, w, name)) for a, b in itertools.product(kbwords(w), repeat=2)]
        for w in (1, 2)
    }
    for label, source in mutants.items():
        b = {**original, "program": source}
        r = verify(b, name)
        normal = normalize(b)
        assert normal["status"] == "normalized", (name, label, normal)
        nf = frozen(normal["certificate"]["normal_form"])
        funcs = parse_bundle(b)
        sound = True
        for w in (1, 2):
            for a, bb, expected in cases[w]:
                raw = evaluate(funcs, (a, bb), w)
                assert raw == expr_value(nf, a + bb, w), (name, label, w)
                sound &= sound_output(raw, expected)
        if r["status"] != "fallback_required":
            assert (r["status"] == "certified") == sound, (name, label, r)
            assert check_certificate(b, name, r["certificate"])["status"] == r["status"]
