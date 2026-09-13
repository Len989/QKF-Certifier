"""Untrusted rewrite search. Checker does not call this module."""

import json

from .certificate import SCHEMA
from .errors import ResourceLimit
from .frontend import expression, parse_bundle
from .kernel import CONTRACT, RULES, apply_rule, children, digest, hashes, table
from .limits import MAX_STEPS


def normalize(e):
    steps = []

    def visit(e, path):
        xs = list(e)
        for i in children(e):
            xs[i] = visit(e[i], path + [i])
        e = tuple(xs)
        while True:
            changed = False
            for rule in RULES:
                try:
                    new = apply_rule(rule, e)
                except ValueError:
                    continue
                if new == e:
                    continue
                if len(steps) >= MAX_STEPS:
                    raise ResourceLimit("proof step limit exceeded")
                steps.append({"path": path.copy(), "rule": rule})
                e = new
                changed = True
                break
            if not changed:
                return e

    return visit(e, []), steps


def produce(bundle, target=None, entry="solution"):
    e = expression(parse_bundle(bundle), entry)
    nf, steps = normalize(e)
    c = dict(
        schema=SCHEMA,
        sources=hashes(bundle),
        entry=entry,
        semantics=CONTRACT,
        initial_hash=digest(e),
        steps=steps,
        normal_form=nf,
        target=target,
    )
    if target is not None:
        c["rows"] = table(nf, target)
    return json.loads(json.dumps(c))
