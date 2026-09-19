"""Restricted signed terminal predicates over one homogeneous int/long word.

This is additive to predicate-v1.  It accepts leading method annotations,
harmless int-to-long decimal widening, signed comparisons against zero, and
pure Boolean &, |, ^.  Calls, shifts, casts, fields, branches and arbitrary
word-to-word order remain unsupported.
"""
import hashlib
import re

from research.observations.model import integer, require
from research.wordexpr.frontend import (
    BINARY, DAG, IDENT, KEYWORDS, UNARY, Unsupported, lex, need
)

CONTRACT = "modular-lsb-signed-word-predicates-v1"
GOAL_SCHEMA = "qkf-signed-word-predicate-goal-v1"
MAX_ATOMS = 12
MODIFIERS = {"public", "private", "protected", "static", "final"}
PREC = {
    "||": 1,
    "&&": 2,
    "|": 3,
    "^": 4,
    "&": 5,
    "==": 6,
    "!=": 6,
    "<": 7,
    "<=": 7,
    ">": 7,
    ">=": 7,
    "+": 8,
    "-": 8,
}


def _strip_leading_annotations(prefix):
    i = 0
    while i < len(prefix) and prefix[i] == "@":
        i += 1
        need(i < len(prefix) and IDENT.fullmatch(prefix[i]), "annotation identifier")
        i += 1
        while i + 1 < len(prefix) and prefix[i] == "." and IDENT.fullmatch(prefix[i + 1]):
            i += 2
        if i < len(prefix) and prefix[i] == "(":
            depth = 0
            while i < len(prefix):
                depth += (prefix[i] == "(") - (prefix[i] == ")")
                i += 1
                if depth == 0:
                    break
            need(depth == 0, "balanced method annotation")
    return i


def select(source, entry, *, word_type):
    require(word_type in {"int", "long"}, "explicit homogeneous word type")
    require(type(entry) is dict and set(entry) == {"class", "method"}, "explicit entry fields")
    require(all(type(v) is str and IDENT.fullmatch(v) for v in entry.values()), "entry identifiers")

    ts = lex(source)
    ws = [row[0] for row in ts]
    stack, closes, depths = [], {}, []
    for i, token in enumerate(ws):
        depths.append(len(stack))
        if token == "{":
            stack.append(i)
        elif token == "}":
            need(bool(stack), "balanced source braces")
            closes[stack.pop()] = i
    need(not stack, "balanced source braces")

    classes = [i for i in range(len(ws) - 1) if ws[i:i + 2] == ["class", entry["class"]]]
    need(len(classes) == 1, "one explicitly selected lexical class")
    class_open = classes[0] + 2
    while class_open < len(ws) and ws[class_open] not in {"{", ";"}:
        class_open += 1
    need(class_open in closes, "selected class body")
    class_end, level = closes[class_open], depths[class_open] + 1

    candidates = []
    for i in range(class_open + 1, class_end):
        if depths[i] != level or ws[i:i + 3] != ["boolean", entry["method"], "("]:
            continue
        j = i + 3
        final_parameter = ws[j:j + 1] == ["final"]
        if final_parameter:
            j += 1
        if j + 3 >= class_end or ws[j] != word_type or not IDENT.fullmatch(ws[j + 1]) \
                or ws[j + 1] in KEYWORDS or ws[j + 2] != ")":
            continue
        body_open = j + 3
        need(ws[body_open] == "{" and body_open in closes, "concrete selected method body")

        boundary = i - 1
        while boundary > class_open and ws[boundary] not in {";", "{", "}"}:
            boundary -= 1
        prefix = ws[boundary + 1:i]
        skipped = _strip_leading_annotations(prefix)
        modifiers = prefix[skipped:]
        need(
            modifiers
            and "static" in modifiers
            and len(modifiers) == len(set(modifiers))
            and set(modifiers) <= MODIFIERS
            and len(set(modifiers) & {"public", "private", "protected"}) <= 1,
            "annotated plain static method modifiers",
        )
        declaration_start = boundary + 1 + skipped
        candidates.append((
            declaration_start,
            body_open,
            closes[body_open],
            ws[j + 1],
            final_parameter,
        ))

    need(len(candidates) == 1, "one selected " + word_type + "-to-boolean method")
    start, body_open, body_end, parameter, final_parameter = candidates[0]
    return (
        ws[body_open + 1:body_end],
        parameter,
        final_parameter,
        source[ts[start][1]:ts[body_end][2]],
        [ts[start][1], ts[body_end][2]],
    )


def formula_size(term, depth=0):
    need(depth < 32, "Boolean expression depth budget")
    if term[0] in {"atom", "literal"}:
        return 1
    size = 1 + sum(formula_size(x, depth + 1) for x in term[1:])
    need(size <= 192, "expanded Boolean expression budget")
    return size


def _literal(token, word_type):
    if word_type == "int":
        need(re.fullmatch(r"(0|[1-9][0-9]*)", token) is not None,
             "unsupported int primary: " + token)
        value = int(token)
        need(value < 2**31, "positive decimal int literal range")
        return value

    if re.fullmatch(r"(0|[1-9][0-9]*)[lL]", token):
        value = int(token[:-1])
        need(value < 2**63, "positive decimal long literal range")
        return value
    need(re.fullmatch(r"(0|[1-9][0-9]*)", token) is not None,
         "unsupported long primary: " + token)
    value = int(token)
    need(value < 2**31, "unsuffixed decimal literal widening to long")
    return value


def read_source(source, entry, word_type):
    ts, parameter, final_parameter, declaration, span = select(
        source, entry, word_type=word_type
    )
    need(len(ts) <= 2048, "selected body token budget")
    dag, atoms, i = DAG(), [], 0
    env = {parameter: ("word", dag.node("input"))}
    finals = {parameter} if final_parameter else set()

    def take(expected=None):
        nonlocal i
        need(i < len(ts) and (expected is None or ts[i] == expected),
             "unsupported signed predicate token at " + str(i))
        token = ts[i]
        i += 1
        return token

    def boolean(op, *args):
        term = [op, *args]
        formula_size(term)
        return ("bool", term)

    def atom(row):
        if row not in atoms:
            need(len(atoms) < MAX_ATOMS, "signed predicate atom budget")
            atoms.append(row)
        return boolean("atom", atoms.index(row))

    def zero_node(node):
        return dag.nodes[node] == ["const", 0]

    def signed_zero(left, op, right):
        need(left[0] == right[0] == "word", "signed comparison word operands")
        if zero_node(right[1]):
            node, normalized = left[1], op
        elif zero_node(left[1]):
            node = right[1]
            normalized = {"<": ">", "<=": ">=", ">": "<", ">=": "<="}[op]
        else:
            raise Unsupported("signed order is currently supported only against zero")
        return atom({"kind": "signed_zero", "node": node, "op": normalized})

    def expression(minimum=1, depth=0):
        need(depth < 32, "signed predicate nesting budget")
        token = take()
        if token in {*UNARY, "!"}:
            typ, arg = expression(10, depth + 1)
            need(typ == ("bool" if token == "!" else "word"), "unary operand type")
            left = boolean("not", arg) if token == "!" else ("word", dag.node(UNARY[token], arg))
        elif token == "(":
            left = expression(1, depth + 1)
            take(")")
        elif token in env:
            left = env[token]
        elif token in {"true", "false"}:
            left = boolean("literal", token == "true")
        else:
            left = ("word", dag.node("const", _literal(token, word_type)))

        while i < len(ts) and PREC.get(ts[i], 0) >= minimum:
            op = take()
            right = expression(PREC[op] + 1, depth + 1)
            if op in {"+", "-"}:
                need(left[0] == right[0] == "word", "arithmetic word operands")
                left = ("word", dag.node(BINARY[op], left[1], right[1]))
            elif op in {"&", "|", "^"}:
                need(left[0] == right[0], "homogeneous bitwise/Boolean operands")
                if left[0] == "word":
                    left = ("word", dag.node(BINARY[op], left[1], right[1]))
                else:
                    left = boolean(
                        {"&": "and", "|": "or", "^": "xor"}[op],
                        left[1],
                        right[1],
                    )
            elif op in {"==", "!="}:
                need(left[0] == right[0] == "word", "word equality operands")
                left = atom({"kind": "eq", "left": left[1], "right": right[1]})
                if op == "!=":
                    left = boolean("not", left[1])
            elif op in {"<", "<=", ">", ">="}:
                left = signed_zero(left, op, right)
            else:
                need(left[0] == right[0] == "bool", "logical Boolean operands")
                left = boolean("and" if op == "&&" else "or", left[1], right[1])
        return left

    root = None
    while i < len(ts):
        token = take()
        if token == "return":
            typ, root = expression()
            need(typ == "bool", "Boolean final result required")
            take(";")
            need(i == len(ts), "no ignored trailing statements")
            break

        final = token == "final"
        if final:
            token = take()
            need(token in {word_type, "boolean"}, "typed final local")
        declared = token in {word_type, "boolean"}
        local_type = "word" if token == word_type else "bool"
        name = take() if declared else token
        need(
            IDENT.fullmatch(name)
            and name not in KEYWORDS
            and (name not in env if declared else name in env),
            "known distinct local",
        )
        need(name not in finals, "assignment to final variable")
        take("=")
        value = expression()
        take(";")
        expected = local_type if declared else env[name][0]
        need(value[0] == expected, "assignment type; no conversions")
        env[name] = value
        if final:
            finals.add(name)

    need(root is not None, "actual Boolean return required")
    return {
        "contract": CONTRACT,
        "word_type": word_type,
        "entry": dict(entry),
        "nodes": dag.nodes,
        "atoms": atoms,
        "formula": root,
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "declaration_sha256": hashlib.sha256(declaration.encode("utf-8")).hexdigest(),
        "span": span,
    }


SIGNED_GOALS = {"positive", "nonnegative", "negative", "nonpositive"}


def goal(spec):
    require(
        type(spec) is dict
        and set(spec) == {"schema", "contract", "entry", "word_type", "target"},
        "signed predicate goal fields",
    )
    require(
        spec["schema"] == GOAL_SCHEMA and spec["contract"] == CONTRACT,
        "signed predicate goal contract",
    )
    require(spec["word_type"] in {"int", "long"}, "signed predicate goal word type")
    entry = spec["entry"]
    require(
        type(entry) is dict
        and set(entry) == {"class", "method"}
        and all(type(v) is str and IDENT.fullmatch(v) for v in entry.values()),
        "signed predicate goal entry",
    )
    nodes = 0
    maximum = -1

    def visit(term, depth=0):
        nonlocal nodes, maximum
        nodes += 1
        require(depth < 16 and nodes <= 96 and type(term) is list and term
                and type(term[0]) is str, "signed target tree budget")
        op = term[0]
        if op in {"popcount_le", "popcount_eq"}:
            require(len(term) == 2 and integer(term[1], 0, 3), "count threshold 0..3")
            maximum = max(maximum, term[1])
            return
        if op in SIGNED_GOALS:
            require(len(term) == 1, "signed target atom arity")
            return
        require(op in {"not", "and", "or", "xor"}
                and len(term) == (2 if op == "not" else 3),
                "signed target Boolean operator")
        for child in term[1:]:
            visit(child, depth + 1)

    visit(spec["target"])
    return max(1, maximum + 1)


def target_value(term, count, sign):
    op = term[0]
    if op == "popcount_le":
        return count <= term[1]
    if op == "popcount_eq":
        return count == term[1]
    if op == "positive":
        return count > 0 and sign == 0
    if op == "nonnegative":
        return sign == 0
    if op == "negative":
        return sign == 1
    if op == "nonpositive":
        return sign == 1 or count == 0
    if op == "not":
        return not target_value(term[1], count, sign)
    if op == "and":
        return target_value(term[1], count, sign) and target_value(term[2], count, sign)
    if op == "or":
        return target_value(term[1], count, sign) or target_value(term[2], count, sign)
    if op == "xor":
        return target_value(term[1], count, sign) != target_value(term[2], count, sign)
    raise ValueError("unknown signed target operator")
