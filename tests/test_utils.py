from inspect import signature
from types import SimpleNamespace

from park_it.app.utils import get_dep


def test_get_dep_dependency_param_is_typed_request():
    dependency = get_dep("value")
    params = list(signature(dependency).parameters.values())

    assert len(params) == 1
    assert params[0].name == "request"
    assert params[0].annotation == "Request"


def test_get_dep_reads_value_from_request_state():
    dependency = get_dep("value")
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(deps=SimpleNamespace(value="ok")))
    )

    assert dependency(request) == "ok"  # pyright: ignore[reportArgumentType]
