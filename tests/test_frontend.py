import pytest

from qkf_certifier import verify
from qkf_certifier.frontend import INTEGER_TYPE, A


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.replace("transfer.and", "transfer.unknown"),
        lambda s: s.replace("index = 0", "index = 2", 1),
        lambda s: s.replace("is_forward = true", "is_forward = false"),
        lambda s: s.replace("transfer.and", "transfer.an d"),
        lambda s: s + "garbage\n",
        lambda s: s.replace("func.call @partial_solution_0_body", "func.call @missing"),
        lambda s: s.replace("func.call @partial_solution_0_body", "func.call @partial_solution_0"),
        lambda s: s.replace("func.return %10", "func.return %999"),
        lambda s: s.replace('%2 = "transfer.get"', '%1 = "transfer.get"'),
        lambda s: s.replace("-> !transfer.integer", "-> i8", 1),
        lambda s: s.replace("index = 0 : index", "index = 0 : index, injected = 1"),
    ],
)
def test_unsupported_is_not_accepted(bundle, change):
    b = bundle("and")
    b["program"] = change(b["program"])
    assert verify(b, "and")["status"] == "fallback_required"


def test_line_comments_and_crlf(bundle):
    b = bundle("and")
    b["program"] = "// test\r\n" + b["program"].replace(
        "builtin.module {", "builtin.module { // module"
    ).replace("\n", "\r\n")
    assert verify(b, "and")["status"] == "certified"


def test_missing_helper(bundle):
    b = bundle("xor")
    del b["meet"]
    assert verify(b, "xor")["status"] == "fallback_required"


def test_duplicate_helper_definition(bundle):
    b = bundle("xor")
    b["duplicate"] = b["meet"]
    assert verify(b, "xor")["status"] == "fallback_required"


def test_unused_wrong_call_result_type(bundle):
    b = bundle("xor")
    lines = b["program"].splitlines()
    i = next(i for i, label_text in enumerate(lines) if "= func.call @meet(" in label_text)
    lines[i] = lines[i].rsplit(" -> ", 1)[0] + " -> i1"
    lines[i + 1] = lines[i + 1].replace("%4", "%2")
    b["program"] = "\n".join(lines)
    assert verify(b, "xor")["status"] == "fallback_required"


def test_exponential_ssa_tree_is_bounded():
    lines = [
        "builtin.module {",
        f"func.func @solution(%a: {A}, %b: {A}) -> {A} {{",
        f'%v0 = "transfer.get"(%a) {{index=0:index}} : ({A}) -> {INTEGER_TYPE}',
    ]
    for i in range(1, 30):
        lines.append(
            f'%v{i} = "transfer.or"(%v{i - 1}, %v{i - 1}) : ({INTEGER_TYPE}, {INTEGER_TYPE}) -> {INTEGER_TYPE}'
        )
    lines += [
        f'%r = "transfer.make"(%v29, %v29) : ({INTEGER_TYPE}, {INTEGER_TYPE}) -> {A}',
        f"func.return %r : {A}",
        "}",
        "}",
    ]
    r = verify({"program": "\n".join(lines)}, "or")
    assert r["status"] == "fallback_required" and "limit" in r["reason"]


def test_unknown_target_is_not_guessed(bundle):
    assert verify(bundle("and"), "add")["status"] == "fallback_required"
