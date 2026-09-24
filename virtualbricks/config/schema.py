# -*- test-case-name: virtualbricks.tests.config.test_schema -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2019 Virtualbricks team

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

"""
Declarative configuration schemas.

A schema is an attrs class whose fields are declared with :func:`field`. The
kind of a field checks its values, converts them to and from TOML data and
parses the text typed in the console. Values are checked when an instance is
created and whenever a field is assigned.
"""

import ipaddress
import re

import attr

__all__ = [
    "Bool",
    "Choice",
    "Float",
    "IPv4",
    "Int",
    "Kind",
    "ListOf",
    "Mac",
    "Path",
    "Record",
    "Ref",
    "Str",
    "default",
    "define",
    "dump",
    "field",
    "fields",
    "kind_of",
    "load",
    "make_class",
    "names",
    "parse",
    "references",
    "rename_references",
    "values",
]

_KEY = "virtualbricks.config.schema"
MAC_PATTERN = r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}"

# attrs 21.2, shipped by Ubuntu 22.04, has no "attrs" namespace yet.
define = attr.define


def _describe(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, list):
        return "an empty list" if not value else "the default list"
    return str(value)


class Kind:
    """How the values of a field are checked, stored and typed."""

    def check(self, value):
        """Raise ValueError if the value can't be stored in the field."""

    def to_data(self, value):
        return value

    def from_data(self, data, report, where):
        self.check(data)
        return data

    def parse(self, text):
        raise ValueError("can't be set from the console")

    def format(self, value):
        raise NotImplementedError("Kind.format")


class Bool(Kind):

    TRUE = frozenset(("true", "yes", "on", "1"))
    FALSE = frozenset(("false", "no", "off", "0"))

    def check(self, value):
        if not isinstance(value, bool):
            raise ValueError(f"{value!r} is not true or false")

    def parse(self, text):
        lowered = text.strip().lower()
        if lowered in self.TRUE:
            return True
        if lowered in self.FALSE:
            return False
        raise ValueError(f"{text!r} is not true or false")

    def format(self, value):
        return "true" if value else "false"


class _Number(Kind):

    types = (int,)
    type_name = "an integer"

    def __init__(self, min=None, max=None):
        self.min = min
        self.max = max

    def check(self, value):
        if isinstance(value, bool) or not isinstance(value, self.types):
            raise ValueError(f"{value!r} is not {self.type_name}")
        if self.min is not None and self.max is not None:
            if not self.min <= value <= self.max:
                raise ValueError(f"{value} is outside {self.min}–{self.max}")
        elif self.min is not None and value < self.min:
            raise ValueError(f"{value} is less than {self.min}")
        elif self.max is not None and value > self.max:
            raise ValueError(f"{value} is more than {self.max}")

    def parse(self, text):
        try:
            value = self.types[0](text.strip())
        except ValueError:
            raise ValueError(f"{text!r} is not {self.type_name}") from None
        self.check(value)
        return value

    def format(self, value):
        return str(value)


class Int(_Number):
    pass


class Float(_Number):

    types = (float, int)
    type_name = "a number"

    def to_data(self, value):
        return float(value)

    def from_data(self, data, report, where):
        self.check(data)
        return float(data)


class Str(Kind):
    """A string, optionally matching a pattern unless it's empty."""

    def __init__(self, pattern=None, what="valid"):
        self.pattern = None if pattern is None else re.compile(pattern)
        self.what = what

    def check(self, value):
        if not isinstance(value, str):
            raise ValueError(f"{value!r} is not a string")
        if value and self.pattern and not self.pattern.fullmatch(value):
            raise ValueError(f'"{value}" is not {self.what}')

    def parse(self, text):
        self.check(text)
        return text

    def format(self, value):
        return f'"{value}"'


class Path(Str):
    """A file or directory path."""


class Ref(Str):
    """The name of an image, event or socket; empty means none."""

    def __init__(self, target):
        super().__init__()
        self.target = target


class Mac(Str):

    def __init__(self):
        super().__init__(MAC_PATTERN, "a MAC address")


class IPv4(Str):
    """An IPv4 address; empty only if the field is optional."""

    def __init__(self, optional=False):
        super().__init__()
        self.optional = optional

    def check(self, value):
        super().check(value)
        if value == "" and self.optional:
            return
        try:
            ipaddress.IPv4Address(value)
        except ValueError:
            raise ValueError(f'"{value}" is not an IPv4 address') from None


class Choice(Str):

    def __init__(self, *choices):
        super().__init__()
        self.choices = choices

    def check(self, value):
        super().check(value)
        if value not in self.choices:
            choices = ", ".join(self.choices)
            raise ValueError(f'"{value}" is not one of {choices}')


class Record(Kind):
    """A nested schema, stored as a TOML table."""

    def __init__(self, cls):
        self.cls = cls

    def check(self, value):
        if not isinstance(value, self.cls):
            raise ValueError(f"{value!r} is not a {self.cls.__name__}")

    def to_data(self, value):
        return dump(value)

    def from_data(self, data, report, where):
        if not isinstance(data, dict):
            raise ValueError(f"{_describe(data)} is not a table")
        return load(self.cls, data, report, where)

    def format(self, value):
        return "{…}"


class ListOf(Kind):
    """A list of values of one kind, optionally of a fixed length."""

    def __init__(self, item, length=None, min_length=None):
        self.item = item
        self.length = length
        self.min_length = min_length

    def _check_length(self, count):
        if self.length is not None and count != self.length:
            raise ValueError(f"has {count} items instead of {self.length}")
        if self.min_length is not None and count < self.min_length:
            raise ValueError(
                f"has {count} items, at least {self.min_length} needed"
            )

    def check(self, value):
        if not isinstance(value, list):
            raise ValueError(f"{value!r} is not a list")
        self._check_length(len(value))
        for item in value:
            self.item.check(item)

    def to_data(self, value):
        return [self.item.to_data(item) for item in value]

    def from_data(self, data, report, where):
        if not isinstance(data, list):
            raise ValueError(f"{_describe(data)} is not a list")
        items = []
        for index, item in enumerate(data):
            item_where = f"{where}[{index}]"
            try:
                items.append(self.item.from_data(item, report, item_where))
            except ValueError as exc:
                report.warning(f"{exc}, item dropped", item_where)
        self._check_length(len(items))
        return items

    def format(self, value):
        return "[" + ", ".join(self.item.format(item) for item in value) + "]"


@attr.define(frozen=True)
class FieldInfo:

    kind = attr.field()
    label = attr.field(default="")
    help = attr.field(default="")
    path = attr.field(default=None)


def _validator(kind):
    def validate(instance, attribute, value):
        try:
            kind.check(value)
        except ValueError as exc:
            raise ValueError(f"{attribute.name}: {exc}") from None

    return validate


def field(
    kind,
    default=attr.NOTHING,
    factory=None,
    label="",
    help="",
    path=None,
):
    """
    Declare a schema field.

    ``path`` is the position of the value in the TOML table when it isn't
    simply the field name, for example ``("disks", "hda", "image")``.
    """

    return attr.field(
        default=default,
        factory=factory,
        validator=_validator(kind),
        metadata={_KEY: FieldInfo(kind, label, help, path)},
    )


def make_class(name, fields, bases=()):
    """Create a schema class from a dict of fields, like :func:`define`."""

    return attr.make_class(
        name,
        fields,
        bases=bases or (object,),
        slots=True,
        on_setattr=attr.setters.validate,
    )


def fields(cls_or_obj):
    cls = cls_or_obj if isinstance(cls_or_obj, type) else type(cls_or_obj)
    return attr.fields(cls)


def names(cls_or_obj):
    return [attribute.name for attribute in fields(cls_or_obj)]


def info(attribute):
    return attribute.metadata[_KEY]


def _path(attribute):
    return info(attribute).path or (attribute.name,)


def kind_of(cls_or_obj, name):
    for attribute in fields(cls_or_obj):
        if attribute.name == name:
            return info(attribute).kind
    raise KeyError(name)


def values(obj):
    """Return the values of all fields, by name."""

    return {name: getattr(obj, name) for name in names(obj)}


def dump(obj, exclude=()):
    """Return the TOML data of an instance, with every field."""

    data = {}
    for attribute in fields(obj):
        if attribute.name in exclude:
            continue
        *parents, key = _path(attribute)
        table = data
        for parent in parents:
            table = table.setdefault(parent, {})
        table[key] = info(attribute).kind.to_data(getattr(obj, attribute.name))
    return data


def _lookup(data, path):
    for key in path:
        if not isinstance(data, dict) or key not in data:
            raise KeyError(key)
        data = data[key]
    return data


def _default_of(attribute):
    if isinstance(attribute.default, attr.Factory):
        return attribute.default.factory()
    return attribute.default


def default(cls_or_obj, name):
    for attribute in fields(cls_or_obj):
        if attribute.name == name:
            return _default_of(attribute)
    raise KeyError(name)


def load(cls, data, report, where="", exclude=(), ignore=()):
    """
    Build an instance from TOML data, reporting problems instead of failing.

    A missing or invalid value takes the default, and an unknown key is
    reported and dropped. ``exclude`` names fields that aren't expected in
    ``data``; ``ignore`` names keys of ``data`` that belong to someone else.
    """

    kwargs = {}
    consumed = set()
    for attribute in fields(cls):
        if attribute.name in exclude:
            continue
        path = _path(attribute)
        consumed.add(path)
        dotted = ".".join(filter(None, (where,) + path))
        kind = info(attribute).kind
        try:
            raw = _lookup(data, path)
        except KeyError:
            default = kind.format(_default_of(attribute))
            report.warning(f"missing, using the default {default}", dotted)
            continue
        try:
            kwargs[attribute.name] = kind.from_data(raw, report, dotted)
        except ValueError as exc:
            default = kind.format(_default_of(attribute))
            report.warning(f"{exc}, using the default {default}", dotted)
    _report_unknown(data, (), consumed, set(ignore), report, where)
    return cls(**kwargs)


def _report_unknown(data, prefix, consumed, ignore, report, where):
    for key, value in data.items():
        path = prefix + (key,)
        if path in consumed or (not prefix and key in ignore):
            continue
        dotted = ".".join(filter(None, (where,) + path))
        is_parent = any(c[: len(path)] == path for c in consumed)
        if isinstance(value, dict) and is_parent:
            _report_unknown(value, path, consumed, ignore, report, where)
        else:
            report.warning("unknown field, dropped", dotted)


def parse(cls_or_obj, name, text):
    """Convert the text typed in the console for a field; KeyError if unknown."""

    return kind_of(cls_or_obj, name).parse(text)


def references(obj):
    """Yield ``(name, target, value)`` for each reference field that is set."""

    for attribute in fields(obj):
        kind = info(attribute).kind
        value = getattr(obj, attribute.name)
        if isinstance(kind, Ref) and value:
            yield attribute.name, kind.target, value


def rename_references(obj, target, old, new):
    """Point the references to ``old`` at ``new``; return True if any moved."""

    changed = False
    for name, ref_target, value in list(references(obj)):
        if ref_target == target and value == old:
            setattr(obj, name, new)
            changed = True
    return changed
