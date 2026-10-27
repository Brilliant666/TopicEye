"""Reuse validated inputs within one synchronous public read, never across requests.

The process cache still owns its existing freshness/signature rules. This scope
only avoids reading the same input repeatedly while constructing one response;
writers and background work do not enter it. Nested read helpers share the
scope, while each caller receives an isolated copy of memoized values.
"""

from contextvars import ContextVar
from copy import deepcopy
from functools import wraps

_inputs: ContextVar[dict | None] = ContextVar("rardar_public_read_inputs", default=None)


def read_scoped(function):
    @wraps(function)
    def read(*args, **kwargs):
        if _inputs.get() is not None:
            return function(*args, **kwargs)
        token = _inputs.set({})
        try:
            return function(*args, **kwargs)
        finally:
            _inputs.reset(token)

    return read


def once(key: tuple, build):
    values = _inputs.get()
    if values is None:
        return build()
    if key not in values:
        values[key] = build()
    return deepcopy(values[key])
