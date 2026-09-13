"""Public API. Only ``certified`` is an all-positive-width soundness verdict."""

import itertools

from .certificate import validate
from .errors import InvalidInput, Unsupported
from .frontend import expression, parse_bundle
from .kernel import CONTRACT, KB, bit, check, children, coordinate, replay
from .producer import produce

TARGETS = ("and", "or", "xor")


def _arguments(sources, entry):
    if (
        not isinstance(sources, dict)
        or not sources
        or any(type(k) is not str or not k or type(v) is not str for k, v in sources.items())
    ):
        raise InvalidInput("sources must map nonempty labels to source text")
    if type(entry) is not str or not entry:
        raise InvalidInput("entry must be a nonempty function name")


def _base(status, entry, target):
    return dict(
        schema="qkf-result-v1",
        status=status,
        entry=entry,
        target=target,
        all_positive_widths=False,
        optimal=None,
        semantics=CONTRACT,
        compiler_lowering_verified=False,
    )


def _witness(row, target):
    if row is None:
        return None
    a, b, out = row["a"], row["b"], row["out"]
    for x, y in itertools.product((0, 1), repeat=2):
        if x & a[0] or x & a[1] != a[1] or y & b[0] or y & b[1] != b[1]:
            continue
        value = x & y if target == "and" else x | y if target == "or" else x ^ y
        if value & out[0] or value & out[1] != out[1]:
            return dict(width=1, a=a, b=b, x=x, y=y, concrete_result=value, output_masks=out)
    raise RuntimeError("internal error: unsound row lacks a witness")


def check_certificate(sources, target, certificate, entry="solution"):
    """Replay an externally supplied proof against explicit source and target.

    ``target=None`` accepts only a normalization certificate, never a soundness
    certificate. Malformed or mismatched proofs raise InvalidCertificate.
    """
    _arguments(sources, entry)
    validate(certificate)
    if target is None:
        if certificate["target"] is not None:
            from .errors import InvalidCertificate

            raise InvalidCertificate("expected normalization-only certificate")
        replay(sources, entry, certificate)
        result = _base("normalized", entry, None)
        result["normalization_verified"] = True
    else:
        if target not in TARGETS:
            raise Unsupported("supported targets are and, or, xor")
        checked = check(sources, target, certificate, entry)
        result = _base(checked["status"], entry, target)
        result.update(
            all_positive_widths=checked["all_positive_widths"],
            optimal=checked["optimal"],
            witness=_witness(checked["witness"], target),
        )
    result["rewrite_steps"] = len(certificate["steps"])
    result["source_hashes"] = certificate["sources"].copy()
    return result


def verify(sources, target, entry="solution"):
    """Generate and independently replay a proof, or return fallback_required.

    The returned dictionary includes ``certificate`` only when a full proof was
    produced. A soundness refutation also has a checkable certificate and witness.
    """
    _arguments(sources, entry)
    if type(target) is not str or not target:
        raise InvalidInput("target must be a nonempty string")
    try:
        if target not in TARGETS:
            raise Unsupported("supported targets are and, or, xor")
        certificate = produce(sources, target, entry)
        result = check_certificate(sources, target, certificate, entry)
        result["certificate"] = certificate
        return result
    except Unsupported as exc:
        result = _base("fallback_required", entry, target)
        result["reason"] = str(exc)
        return result


def normalize(sources, entry="solution"):
    """Prove source-to-normal-form equality; this does not prove a target."""
    _arguments(sources, entry)
    try:
        certificate = produce(sources, None, entry)
        result = check_certificate(sources, None, certificate, entry)
        result["certificate"] = certificate
        return result
    except Unsupported as exc:
        result = _base("fallback_required", entry, None)
        result["reason"] = str(exc)
        return result


def inspect(sources, entry="solution"):
    """Describe a checked normal form and its exact coordinatewise signature."""
    result = normalize(sources, entry)
    if result["status"] != "normalized":
        return result
    certificate = result.pop("certificate")
    from .kernel import frozen

    nf = frozen(certificate["normal_form"])

    def nodes(root):
        seen = set()
        todo = [root]
        while todo:
            e = todo.pop()
            if e in seen:
                continue
            seen.add(e)
            todo.extend(e[i] for i in children(e))
        return seen

    before = expression(parse_bundle(sources), entry)
    ns = nodes(nf)
    result["original_unique_nodes"] = len(nodes(before))
    result["normalized_unique_nodes"] = len(ns)
    result["residual_operations"] = sorted(
        {e[0] for e in ns if e[0] != "pair" and not coordinate(e)}
    )
    result["coordinatewise"] = nf[0] == "pair" and all(coordinate(x) for x in nf[1:])
    if result["coordinatewise"]:
        value = 0
        for i, (a, b) in enumerate(itertools.product(KB, repeat=2)):
            for j, e in enumerate(nf[1:]):
                value |= bit(e, a + b) << (2 * i + j)
        result["semantic_signature"] = f"{value:05x}"
    return result
