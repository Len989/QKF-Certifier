"""Exact development population, frozen before comparative execution."""
from pathlib import Path

BASE = '4b22de68f28dc0874523dbbfae64cbcb9343c448'
SOURCE = Path(__file__).resolve().parents[1] / 'graal/previous/baseline/source/IntegerStamp.java'
ROUTES = ('forcing', 'no_saturation', 'direct_seeds', 'direct_cell')


def request(goals=None, label=None):
    return dict(schema='qkf-local-forcing-request-v1',
                profile='graal-ascending-physical-phases-v1',
                label=[0, 1, 1, 0] if label is None else label,
                goals=[[3, 0]] if goals is None else goals)


def cases():
    source = SOURCE.read_text()

    def case(name, text=source, req=None, expected=None, work=5_000_000):
        return dict(name=name, source=text, request=request() if req is None else req,
                    limits=dict(max_work=work), expected=dict(zip(ROUTES, expected or
                        ['certified', 'unresolved', 'certified', 'certified'])))

    goals = [[3, 0], [1, 0], [4, 5], [5, 5]]
    yield case('pilot_1')
    yield case('pilot_4', req=request(goals))
    yield case('pilot_16', req=request(goals * 4))
    yield case('input_zero', req=request(label=[0, 1, 0, 0]),
               expected=['refuted', 'unresolved', 'refuted', 'refuted'])
    yield case('output_one', req=request(label=[0, 1, 1, 1]),
               expected=['refuted', 'unresolved', 'refuted', 'refuted'])
    needle = 'else if ((bit & optionalBits) != 0) {\n                            newLowerBound += bit;'
    if source.count(needle) != 1:
        raise ValueError('registered first-repair mutation anchor')
    yield case('first_or', text=source.replace(needle, needle.replace('+=', '|=')))
    yield case('alpha_renamed', text=source.replace('newLowerBound', 'candidateFloor'))
    yield case('wrong_value', req=request([[3, 5]]),
               expected=['refuted', 'unresolved', 'refuted', 'refuted'])
    yield case('mandatory_gap', req=request([[1, 1]], [1, 1, 1, 1]),
               expected=['unresolved', 'unresolved', 'certified', 'certified'])
    yield case('unsupported_return', text=source.replace('return newLowerBound;', 'return ~newLowerBound;'),
               expected=['unsupported'] * 4)
    yield case('forcing_budget', work=0,
               expected=['budget_exhausted', 'unresolved', 'certified', 'certified'])
