#!/usr/bin/env python3
# -*- test-case-name: virtualbricks.tests.test_tools -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2026 Virtualbricks team
#
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
How much of the code has type annotations, module by module.

    python tools/typecoverage.py                  the most typed first
    python tools/typecoverage.py --sort name      in the order of the paths
    python tools/typecoverage.py e2e virtualbricks/config

A function has a slot for each parameter and one for what it returns. The
first parameter of a method, self or cls, has none, and neither has the
return of an __init__ with parameters: mypy takes such an __init__ as typed
when its parameters are. The percentage of a module is that of its slots
that are annotated; "typed" counts its functions with every slot annotated.

The arguments are folders or files, virtualbricks by default. In a folder,
the files under a folder named tests are left out.
"""

import argparse
import ast
import os
import pathlib
import sys
from collections.abc import Iterator, Sequence
from typing import NamedTuple, TypeAlias

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

Function: TypeAlias = ast.FunctionDef | ast.AsyncFunctionDef


class Coverage(NamedTuple):
    """The annotations of a module."""

    name: str
    lines: int
    functions: int
    typed: int
    slots: int
    annotated: int

    @property
    def percent(self) -> float | None:
        if self.slots == 0:
            return None
        return 100 * self.annotated / self.slots


def functions(tree: ast.AST) -> Iterator[tuple[Function, bool]]:
    """Every function of a tree, and whether it's a method."""

    def walk(node: ast.AST, in_class: bool) -> Iterator[tuple[Function, bool]]:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield child, in_class
                yield from walk(child, False)
            elif isinstance(child, ast.ClassDef):
                yield from walk(child, True)
            else:
                yield from walk(child, in_class)

    return walk(tree, False)


def is_static(function: Function) -> bool:
    return any(
        isinstance(d, ast.Name) and d.id == "staticmethod"
        for d in function.decorator_list
    )


def slots(function: Function, method: bool) -> tuple[int, int]:
    """The slots of a function, and how many of them are annotated."""
    args = function.args
    params = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    params += [a for a in (args.vararg, args.kwarg) if a is not None]
    if method and not is_static(function) and params:
        del params[0]
    total = len(params)
    annotated = sum(p.annotation is not None for p in params)
    if function.returns is not None:
        total += 1
        annotated += 1
    elif not (function.name == "__init__" and params):
        total += 1
    return total, annotated


def measure(source: str, name: str) -> Coverage:
    """The coverage of the source of a module."""
    count = typed = total = annotated = 0
    for function, method in functions(ast.parse(source, name)):
        s, a = slots(function, method)
        count += 1
        typed += s == a
        total += s
        annotated += a
    lines = len(source.splitlines())
    return Coverage(name, lines, count, typed, total, annotated)


def modules(paths: Sequence[str]) -> Iterator[tuple[pathlib.Path, str]]:
    """The modules of the paths, with the names they are shown with."""
    for path in map(pathlib.Path, paths):
        if path.is_file():
            yield path, str(path)
            continue
        for module in sorted(path.rglob("*.py")):
            relative = module.relative_to(path)
            if "tests" not in relative.parts[:-1]:
                yield module, str(relative)


def percent(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}"


def table(rows: list[Coverage], by_name: bool) -> str:
    """The rows as a table, with the totals of all of them."""
    if not by_name:
        # the most typed first; the modules without functions last
        rows = sorted(
            rows, key=lambda r: (r.percent is None, -(r.percent or 0), r.name)
        )
    total = Coverage(
        "total",
        sum(r.lines for r in rows),
        sum(r.functions for r in rows),
        sum(r.typed for r in rows),
        sum(r.slots for r in rows),
        sum(r.annotated for r in rows),
    )
    width = max(len(r.name) for r in [*rows, total])
    header = f"{'module':{width}} {'lines':>6} {'functions':>9} {'typed':>6}"
    lines = [f"{header}      %"]
    for r in [*rows, total]:
        lines.append(
            f"{r.name:{width}} {r.lines:6} {r.functions:9} {r.typed:6}"
            f" {percent(r.percent):>6}"
        )
    lines.insert(-1, "-" * len(lines[0]))
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="How much of the code has type annotations."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="PATH",
        default=[os.path.join(ROOT, "virtualbricks")],
        help="a folder or a file (default: virtualbricks)",
    )
    parser.add_argument(
        "--sort",
        choices=["percent", "name"],
        default="percent",
        help="the most typed first, or in the order of the paths",
    )
    args = parser.parse_args(argv)
    for path in args.paths:
        if not os.path.exists(path):
            parser.error(f"{path}: no such file or folder")
    rows = [
        measure(module.read_text(encoding="utf-8"), name)
        for module, name in modules(args.paths)
    ]
    if not rows:
        parser.error("no Python modules")
    print(table(rows, args.sort == "name"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
