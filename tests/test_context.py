from string import ascii_lowercase, ascii_uppercase

import pytest

from config_utils.context import DictContext, ListContext


class NamedObj:
    def __init__(self, name):
        self.name = name


class ImplNamedObj:
    def __init__(self, name):
        self.__name__ = name


@pytest.fixture
def named_obj():
    return NamedObj("named_obj")


@pytest.fixture
def impl_named_obj():
    return ImplNamedObj("impl_named_obj")


@pytest.fixture
def item():
    return ("key", "value")


@pytest.fixture(
    params=(
        [(1, 1), (2, 2), (3, 3)],
        tuple(zip("abcdefghij", range(10))),
        list(zip(ascii_lowercase, ascii_uppercase)),
    )
)
def items(request):
    return request.param


@pytest.fixture
def list_context(items):
    return ListContext(item[0] for item in items)


@pytest.fixture
def dict_context(items):
    return DictContext({item[0]: item[1] for item in items})


class TestListContext:
    def test_constructor(self, list_context, items):
        assert isinstance(list_context, ListContext)
        assert len(list_context) == len(list(items))

    def test_merge(self, list_context, item):
        lc = ListContext([item])
        list_context.merge(lc)
        assert item in list_context

    def test_insert(self, list_context, item):
        list_context.insert(item)
        assert item in list_context

    def test_insert_sub_ListContext(self, list_context):
        val = "value"
        lc = ListContext([val])
        list_context.insert(lc)
        assert lc in list_context
        assert val not in list_context

    def test_join(self, list_context, item):
        lc = ListContext(["value"])
        list_context.join(item)
        assert item in list_context
        list_context.join(lc)
        assert "value" in list_context


class TestDictContext:
    def test_constructor(self, dict_context, items):
        assert isinstance(dict_context, DictContext)
        assert len(dict_context) == len(items)
        for item in items:
            assert item[0] in dict_context
            assert dict_context[item[0]] == item[1]

    def test_merge(self, dict_context, item, items):
        dc = DictContext({item[0]: item[1]})
        dict_context.merge(dc)
        assert len(dict_context) == 1 + len(items)
        assert dict_context[item[0]] == item[1]

    def test_insert(self, dict_context, item, items):
        dict_context.insert(item[1], item[0])
        assert dict_context[item[0]] == item[1]

    def test_insert_nokey(self, dict_context, named_obj, impl_named_obj):
        obj = object()
        dict_context.insert(obj)
        dict_context.insert(named_obj)
        dict_context.insert(impl_named_obj)
        assert dict_context[id(obj)] is obj
        assert dict_context[named_obj.name] is named_obj
        assert dict_context[impl_named_obj.__name__] is impl_named_obj

    def test_insert_sub_DictContext(self, dict_context):
        sub = DictContext()
        dict_context.insert(sub, "sub")
        assert dict_context["sub"] is sub
        val = "value"
        dict_context.insert(val, "sub")
        assert val not in dict_context.values()
        assert sub[id(val)] == val

    def test_insert_sub_ListContext(self, dict_context, list_context):
        dict_context.insert(list_context, "sub")
        assert dict_context["sub"] is list_context
        val = "value"
        dict_context.insert(val, "sub")
        assert val not in dict_context.values()
        assert val in list_context

    def test_join(self, dict_context, item, items):
        dict_context.join(item[1], item[0])
        assert dict_context[item[0]] == item[1]
