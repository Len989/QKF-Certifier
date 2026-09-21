"""Owned immutable JSON values and nonserializable internal capabilities.

These are an API boundary, not a sandbox against hostile Python reflection.
Only plain JSON is accepted at admission; no serialized checked flags exist.
"""
from types import MappingProxyType
from research.ground_query.schema import require

_KEY = object()


class Sequence(tuple):
    """Immutable list with JSON-list equality for unchanged native-rule readers."""
    __slots__ = ()

    def __eq__(self, other):
        return isinstance(other, (list, tuple)) and tuple.__eq__(self, tuple(other))

    def __ne__(self, other):
        return not self == other

    __hash__ = tuple.__hash__


def own(value):
    if type(value) is dict:
        return MappingProxyType({k: own(v) for k, v in value.items()})
    if type(value) in (list, tuple):
        return Sequence(own(v) for v in value)
    require(type(value) in (str, int, bool, type(None)), 'internal JSON value')
    return value


def plain(value):
    if isinstance(value, MappingProxyType):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [plain(v) for v in value]
    return value


class Capability:
    __slots__ = ()

    def __init__(self, seal=None, **values):
        require(seal is _KEY, 'internal checked capability; use admission')
        for name, value in values.items():
            object.__setattr__(self, name, value)

    def __reduce_ex__(self, protocol):
        raise TypeError('internal checked capabilities cannot be serialized')
