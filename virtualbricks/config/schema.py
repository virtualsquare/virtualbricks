# -*- test-case-name: virtualbricks.tests.config.test_schema -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2026 Virtualbricks team

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

The help of a field says what it's for; with the range or the choices of its
kind and its default, it's the comment above its key in the files, see
:func:`notes`.

A field can go with another: ``when=("use_vnc", True)`` says that it counts
only while use_vnc is true, and only while use_vnc counts itself, see
:func:`why_unused`. The panels grey the fields out of use, the files' comments
say what each goes with, and the console marks those out of use. A field out
of use keeps its value.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable, Collection, Iterator
from functools import partial
from typing import Any, ClassVar, Generic, TypeVar, cast

import attr

# attrs 21.2, shipped by Ubuntu 22.04, has no "attrs" namespace yet. Imported,
# not assigned, so that mypy's plugin of attrs knows the classes it makes.
from attr import define

from virtualbricks.config.report import Report
from virtualbricks.config.tomlfile import Note, Notes, Table, Value
from virtualbricks.nic import MAC_PATTERN

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
    "define",
    "dump_record",
    "field",
    "field_default",
    "field_names",
    "field_values",
    "fields",
    "info_of",
    "key_of",
    "kind_of",
    "load_record",
    "notes",
    "parse_value",
    "references",
    "rename_references",
    "why_unused",
]

_KEY = "virtualbricks.config.schema"

# The values of a field.
T = TypeVar("T")
# The values of a number field.
N = TypeVar("N", int, float)
# A schema class.
S = TypeVar("S")


def _describe(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, list):
        return "an empty list" if not value else "the default list"
    return str(value)


class Kind(Generic[T]):
    """How the values of a field, of type T, are checked, stored and typed."""

    def check(self, value: object) -> None:
        """Raise ValueError if the value can't be stored in the field."""

    def to_data(self, value: T) -> Value:
        # the data of most kinds is the value itself
        return cast("Value", value)

    def from_data(self, data: Value, report: Report, where: str) -> T:
        self.check(data)
        return cast(T, data)

    def parse(self, text: str) -> T:
        raise ValueError("can't be set from the console")

    def format(self, value: T) -> str:
        raise NotImplementedError("Kind.format")

    def describe(self) -> str:
        """The range or the choices of the values, as ``1-128``; or ""."""

        return ""

    def notes(self, data: Value) -> Notes:
        """The notes of the keys inside the data of a value, by their path."""

        return {}


class Bool(Kind[bool]):

    TRUE = frozenset(("true", "yes", "on", "1"))
    FALSE = frozenset(("false", "no", "off", "0"))

    def check(self, value: object) -> None:
        if not isinstance(value, bool):
            raise ValueError(f"{value!r} is not true or false")

    def parse(self, text: str) -> bool:
        lowered = text.strip().lower()
        if lowered in self.TRUE:
            return True
        if lowered in self.FALSE:
            return False
        raise ValueError(f"{text!r} is not true or false")

    def format(self, value: bool) -> str:
        return "true" if value else "false"


class _Number(Kind[N]):

    types: ClassVar[tuple[type[int] | type[float], ...]] = (int,)
    type_name = "an integer"

    def __init__(self, min: N | None = None, max: N | None = None) -> None:
        self.min: N | None = min
        self.max: N | None = max

    def check(self, value: object) -> None:
        if isinstance(value, bool) or not isinstance(value, self.types):
            raise ValueError(f"{value!r} is not {self.type_name}")
        if self.min is not None and self.max is not None:
            if not self.min <= value <= self.max:
                raise ValueError(f"{value} is outside {self.min}–{self.max}")
        elif self.min is not None and value < self.min:
            raise ValueError(f"{value} is less than {self.min}")
        elif self.max is not None and value > self.max:
            raise ValueError(f"{value} is more than {self.max}")

    def parse(self, text: str) -> N:
        try:
            value = self.types[0](text.strip())
        except ValueError:
            raise ValueError(f"{text!r} is not {self.type_name}") from None
        self.check(value)
        # the first of the types is the type of the values
        return cast(N, value)

    def format(self, value: N) -> str:
        return str(value)

    def describe(self) -> str:
        if self.min is not None and self.max is not None:
            return f"{self.min}-{self.max}"
        if self.min is not None:
            return f"{self.min} or more"
        if self.max is not None:
            return f"{self.max} or less"
        return ""


class Int(_Number[int]):
    pass


class Float(_Number[float]):

    types = (float, int)
    type_name = "a number"

    def to_data(self, value: float) -> float:
        return float(value)

    def from_data(self, data: Value, report: Report, where: str) -> float:
        # an integer is a number too, stored as a float
        return float(super().from_data(data, report, where))


class Str(Kind[str]):
    """
    A string, optionally matching a pattern unless it's empty.

    A required string can't be empty.
    """

    def __init__(
        self,
        pattern: str | None = None,
        what: str = "valid",
        required: bool = False,
    ) -> None:
        self.pattern = None if pattern is None else re.compile(pattern)
        self.what = what
        self.required = required

    def check(self, value: object) -> None:
        if not isinstance(value, str):
            raise ValueError(f"{value!r} is not a string")
        if self.required and not value:
            raise ValueError("can't be empty")
        if value and self.pattern and not self.pattern.fullmatch(value):
            raise ValueError(f'"{value}" is not {self.what}')

    def parse(self, text: str) -> str:
        self.check(text)
        return text

    def format(self, value: str) -> str:
        return f'"{value}"'


class Path(Str):
    """A file or directory path."""


class Ref(Str):
    """The name of an image, event or socket; empty means none."""

    def __init__(self, target: str) -> None:
        super().__init__()
        self.target = target


class Mac(Str):

    def __init__(self) -> None:
        super().__init__(MAC_PATTERN, "a MAC address")


class IPv4(Str):
    """An IPv4 address; empty only if the field is optional."""

    def __init__(self, optional: bool = False) -> None:
        super().__init__()
        self.optional = optional

    def check(self, value: object) -> None:
        super().check(value)
        if value == "" and self.optional:
            return
        try:
            ipaddress.IPv4Address(value)
        except ValueError:
            raise ValueError(f'"{value}" is not an IPv4 address') from None


class Choice(Str):

    def __init__(self, *choices: str) -> None:
        super().__init__()
        self.choices = choices

    def check(self, value: object) -> None:
        super().check(value)
        if value not in self.choices:
            choices = ", ".join(self.choices)
            raise ValueError(f'"{value}" is not one of {choices}')

    def describe(self) -> str:
        *others, last = self.choices
        return f"{', '.join(others)} or {last}" if others else last


class Record(Kind[S]):
    """
    A nested schema, stored as a TOML table.

    The fields named in ``exclude`` are not stored: they keep their default
    when the table is read, and in the table they are unknown fields.
    """

    def __init__(self, cls: type[S], exclude: Collection[str] = ()) -> None:
        self.cls = cls
        self.exclude = frozenset(exclude)

    def check(self, value: object) -> None:
        if not isinstance(value, self.cls):
            raise ValueError(f"{value!r} is not a {self.cls.__name__}")

    def to_data(self, value: S) -> Table:
        return dump_record(value, exclude=self.exclude)

    def from_data(self, data: Value, report: Report, where: str) -> S:
        if not isinstance(data, dict):
            raise ValueError(f"{_describe(data)} is not a table")
        return load_record(self.cls, data, report, where, exclude=self.exclude)

    def format(self, value: S) -> str:
        return "{…}"

    def notes(self, data: Value) -> Notes:
        if not isinstance(data, dict):
            return {}
        return notes(self.cls, data, exclude=self.exclude)


class ListOf(Kind[list[T]]):
    """A list of values of one kind, optionally of a fixed length."""

    def __init__(
        self,
        item: Kind[T],
        length: int | None = None,
        min_length: int | None = None,
    ) -> None:
        self.item = item
        self.length = length
        self.min_length = min_length

    def _check_length(self, count: int) -> None:
        if self.length is not None and count != self.length:
            raise ValueError(f"has {count} items instead of {self.length}")
        if self.min_length is not None and count < self.min_length:
            raise ValueError(
                f"has {count} items, at least {self.min_length} needed"
            )

    def check(self, value: object) -> None:
        if not isinstance(value, list):
            raise ValueError(f"{value!r} is not a list")
        self._check_length(len(value))
        for item in value:
            self.item.check(item)

    def to_data(self, value: list[T]) -> list[Value]:
        return [self.item.to_data(item) for item in value]

    def from_data(self, data: Value, report: Report, where: str) -> list[T]:
        if not isinstance(data, list):
            raise ValueError(f"{_describe(data)} is not a list")
        items: list[T] = []
        for index, item in enumerate(data):
            item_where = f"{where}[{index}]"
            try:
                items.append(self.item.from_data(item, report, item_where))
            except ValueError as exc:
                report.warning(f"{exc}, item dropped", item_where)
        self._check_length(len(items))
        return items

    def format(self, value: list[T]) -> str:
        return "[" + ", ".join(self.item.format(item) for item in value) + "]"

    def notes(self, data: Value) -> Notes:
        if not isinstance(data, list):
            return {}
        return {
            (index, *path): note
            for index, item in enumerate(data)
            for path, note in self.item.notes(item).items()
        }


@attr.define(frozen=True)
class FieldInfo:

    # the kind of any field, whatever the type of its values
    kind: Kind[Any] = attr.field()
    label: str = attr.field(default="")
    help: str = attr.field(default="")
    path: tuple[str, ...] | None = attr.field(default=None)
    # the field that this one goes with, and the value it needs
    when: tuple[str, object] | None = attr.field(default=None)


def _validator(
    kind: Kind[T],
) -> Callable[[object, attr.Attribute[object], object], None]:
    def validate(
        instance: object, attribute: attr.Attribute[object], value: object
    ) -> None:
        try:
            kind.check(value)
        except ValueError as exc:
            raise ValueError(f"{attribute.name}: {exc}") from None

    return validate


def field(
    kind: Kind[T],
    default: object = attr.NOTHING,
    factory: Callable[[], T] | None = None,
    label: str = "",
    help: str = "",
    path: tuple[str, ...] | None = None,
    when: tuple[str, object] | None = None,
) -> T:
    """
    Declare a schema field.

    ``path`` is the position of the value in the TOML table when it isn't
    simply the field name, for example ``("disks", "hda", "image")``.
    ``when`` is the field of the same schema that this one goes with, and the
    value that field needs for this one to count, as ``("use_vnc", True)``.
    """

    field = attr.field(
        default=default,
        factory=factory,
        validator=_validator(kind),
        metadata={_KEY: FieldInfo(kind, label, help, path, when)},
    )
    # in the body of the class, a field stands for its values
    return cast(T, field)


def fields(cls_or_obj: object) -> tuple[attr.Attribute[object], ...]:
    cls = cls_or_obj if isinstance(cls_or_obj, type) else type(cls_or_obj)
    return attr.fields(cls)


def field_names(cls_or_obj: object) -> list[str]:
    return [attribute.name for attribute in fields(cls_or_obj)]


def field_info(attribute: attr.Attribute[object]) -> FieldInfo:
    return attribute.metadata[_KEY]


def _path(attribute: attr.Attribute[object]) -> tuple[str, ...]:
    return field_info(attribute).path or (attribute.name,)


def info_of(cls_or_obj: object, name: str) -> FieldInfo:
    """
    What the schema says of a field: its kind, its label, its help and what
    it goes with.
    """

    for attribute in fields(cls_or_obj):
        if attribute.name == name:
            return field_info(attribute)
    raise KeyError(name)


def kind_of(cls_or_obj: object, name: str) -> Kind[object]:
    return info_of(cls_or_obj, name).kind


def key_of(cls_or_obj: object, name: str) -> str:
    """The dotted key of a field in its table, as ``disks.hda.image``."""

    for attribute in fields(cls_or_obj):
        if attribute.name == name:
            return ".".join(_path(attribute))
    raise KeyError(name)


def field_values(obj: object) -> dict[str, object]:
    """Return the values of all fields, by name."""

    return {name: getattr(obj, name) for name in field_names(obj)}


def dump_record(obj: object, exclude: Collection[str] = ()) -> Table:
    """Return the TOML data of an instance, with every field."""

    data: Table = {}
    for attribute in fields(obj):
        if attribute.name in exclude:
            continue
        *parents, key = _path(attribute)
        table = data
        for parent in parents:
            # the tables of the parents are made here
            table = cast("Table", table.setdefault(parent, {}))
        table[key] = field_info(attribute).kind.to_data(
            getattr(obj, attribute.name)
        )
    return data


def _lookup(data: Value, path: tuple[str, ...]) -> Value:
    for key in path:
        if not isinstance(data, dict) or key not in data:
            raise KeyError(key)
        data = data[key]
    return data


def _default_of(attribute: attr.Attribute[object]) -> object:
    # attrs types Factory as the function that makes the default
    if isinstance(attribute.default, attr.Factory):  # type: ignore[arg-type]
        return attribute.default.factory()  # type: ignore[attr-defined]
    return attribute.default


def field_default(cls_or_obj: object, name: str) -> object:
    for attribute in fields(cls_or_obj):
        if attribute.name == name:
            return _default_of(attribute)
    raise KeyError(name)


def why_unused(
    obj: object, name: str, get: Callable[[str], object] | None = None
) -> str | None:
    """
    The field that keeps a field out of use, or None if the field is in use.

    A field is in use unless it goes with another, by its ``when``, and that
    field hasn't the value it needs or is out of use itself: initrd goes with
    use_initrd, which goes with use_kernel. The field returned is the first
    along that chain without the value; a chain that comes back to a field
    ends there. ``get`` reads the value of a field, getattr() by default.
    """

    if get is None:
        get = partial(getattr, obj)
    seen: set[str] = set()
    while name not in seen:
        seen.add(name)
        when = info_of(obj, name).when
        if when is None:
            return None
        other, value = when
        if get(other) != value:
            return other
        name = other
    return None


def _detail(cls: type[object], attribute: attr.Attribute[object]) -> str:
    """
    The range or the choices of a field, its default and what it goes with,
    as a note says.
    """

    info = field_info(attribute)
    kind = info.kind
    parts = [kind.describe()] if kind.describe() else []
    default = _default_of(attribute)
    data = kind.to_data(default)
    if data == "" or data == []:
        parts.append("default empty")
    elif not isinstance(data, (list, dict)):
        # a table, or a list with items, is left out
        parts.append(f"default {kind.format(default)}")
    if info.when is not None:
        other, value = info.when
        needed = kind_of(cls, other).format(value)
        parts.append(f"used when {key_of(cls, other)} is {needed}")
    return "; ".join(parts)


def field_help(cls_or_obj: object, name: str) -> tuple[str, str]:
    """
    What a field is for, as its help says, and its range or choices, its
    default and what it goes with: the parts of the comment of its key.
    KeyError if there is no such field.
    """

    for attribute in fields(cls_or_obj):
        if attribute.name == name:
            cls = (
                cls_or_obj
                if isinstance(cls_or_obj, type)
                else type(cls_or_obj)
            )
            return field_info(attribute).help, _detail(cls, attribute)
    raise KeyError(name)


def notes(
    cls: type[object], data: Table, exclude: Collection[str] = ()
) -> Notes:
    """
    The note of each key of the data of an instance of the schema, by its
    path in the data as :func:`dump_record` writes it: the help of the field,
    the range or the choices of its kind, its default and the key it goes
    with, and whether the value is the default. The keys inside a record or a
    list of records have theirs too.
    """

    result: dict[tuple[str | int, ...], Note] = {}
    for attribute in fields(cls):
        if attribute.name in exclude:
            continue
        path = _path(attribute)
        try:
            value = _lookup(data, path)
        except KeyError:
            continue
        info = field_info(attribute)
        default = info.kind.to_data(_default_of(attribute))
        result[path] = Note(
            info.help, _detail(cls, attribute), value == default
        )
        for inner, note in info.kind.notes(value).items():
            result[path + inner] = note
    return result


def load_record(
    cls: type[S],
    data: Table,
    report: Report,
    where: str = "",
    exclude: Collection[str] = (),
    ignore: Collection[str] = (),
) -> S:
    """
    Build an instance of a schema from TOML data, reporting the problems
    instead of failing.

    ``cls`` is a schema: a class made with :func:`define` whose fields are
    all declared with :func:`field`, each with a default or a factory. Each
    field's value is read at its path in ``data``, the field's name unless
    :func:`field` gives another, and converted by its kind.

    A missing or invalid value is reported to ``report`` and the field keeps
    its default. A key of ``data`` that no field reads is reported and
    dropped. ``where`` is the dotted path of ``data`` in its file, the prefix
    of the keys in the report, as in ``bricks.sw1``.

    ``exclude`` names the fields that ``data`` doesn't hold: they keep their
    default, and a key of theirs in ``data`` is unknown. ``ignore`` names the
    keys at the top of ``data`` that someone else reads, as ``format``: they
    aren't reported.
    """

    kwargs: dict[str, object] = {}
    consumed: set[tuple[str, ...]] = set()
    for attribute in fields(cls):
        if attribute.name in exclude:
            continue
        path = _path(attribute)
        consumed.add(path)
        dotted = ".".join(filter(None, (where,) + path))
        kind = field_info(attribute).kind
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


def _report_unknown(
    data: Table,
    prefix: tuple[str, ...],
    consumed: set[tuple[str, ...]],
    ignore: set[str],
    report: Report,
    where: str,
) -> None:
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


def parse_value(cls_or_obj: object, name: str, text: str) -> object:
    """Convert the text typed in the console for a field; KeyError if unknown."""

    return kind_of(cls_or_obj, name).parse(text)


def references(obj: object) -> Iterator[tuple[str, str, str]]:
    """Yield ``(name, target, value)`` for each reference field that is set."""

    for attribute in fields(obj):
        kind = field_info(attribute).kind
        value = getattr(obj, attribute.name)
        if isinstance(kind, Ref) and value:
            yield attribute.name, kind.target, value


def rename_references(obj: object, target: str, old: str, new: str) -> bool:
    """Point the references to ``old`` at ``new``; return True if any moved."""

    changed = False
    for name, ref_target, value in list(references(obj)):
        if ref_target == target and value == old:
            setattr(obj, name, new)
            changed = True
    return changed
