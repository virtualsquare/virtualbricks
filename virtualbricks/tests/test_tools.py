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
The scripts of tools/. The tests are skipped when the folder is not there, as
in an installed package.
"""

import contextlib
import importlib.util
import io
import os
import textwrap

from twisted.trial import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
TOOLS = os.path.join(ROOT, "tools")


def load(name):
    """The module of a script of tools/."""
    path = os.path.join(TOOLS, f"{name}.py")
    if not os.path.exists(path):
        raise unittest.SkipTest("the tools of the sources")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTypeCoverage(unittest.TestCase):

    def setUp(self):
        self.tool = load("typecoverage")

    def measure(self, source):
        return self.tool.measure(textwrap.dedent(source), "m.py")

    def write(self, name, source):
        path = os.path.join(self.root, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(textwrap.dedent(source))

    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(self.tool.main(list(argv)), 0)
        return out.getvalue().splitlines()

    def make_tree(self):
        self.root = self.mktemp()
        self.write("typed.py", "def f(a: int) -> int: ...\n")
        self.write("half.py", "def f(a: int): ...\n")
        self.write("untyped.py", "def f(a): ...\n")
        self.write("empty.py", "X = 1\n")
        self.write("tests/test_typed.py", "def test(a): ...\n")

    def test_slots(self):
        """A slot for each parameter and one for the return."""
        coverage = self.measure("""\
            def f(a: int, /, b, *args: str, c=1, **kwargs) -> None:
                pass
            """)
        self.assertEqual(coverage.slots, 6)
        self.assertEqual(coverage.annotated, 3)
        self.assertEqual(coverage.functions, 1)
        self.assertEqual(coverage.typed, 0)
        self.assertEqual(coverage.percent, 50)

    def test_typed(self):
        """A function is typed with every slot annotated."""
        coverage = self.measure("""\
            async def f(a: int) -> int:
                def inner(b):
                    pass
            """)
        self.assertEqual(coverage.functions, 2)
        self.assertEqual(coverage.typed, 1)
        self.assertEqual((coverage.slots, coverage.annotated), (4, 2))

    def test_method(self):
        """The first parameter of a method has no slot."""
        coverage = self.measure("""\
            class C:
                def f(self) -> None:
                    pass

                if True:
                    @classmethod
                    def g(cls, a: int) -> None:
                        pass
            """)
        self.assertEqual((coverage.slots, coverage.annotated), (3, 3))

    def test_static_method(self):
        """The first parameter of a static method has a slot."""
        coverage = self.measure("""\
            class C:
                @staticmethod
                def f(a) -> None:
                    pass
            """)
        self.assertEqual((coverage.slots, coverage.annotated), (2, 1))

    def test_function_in_method(self):
        """A function in a method is not a method."""
        coverage = self.measure("""\
            class C:
                def f(self) -> None:
                    def inner(a) -> None:
                        pass
            """)
        self.assertEqual((coverage.slots, coverage.annotated), (3, 2))

    def test_init(self):
        """An __init__ with parameters needs no return, one without does."""
        coverage = self.measure("""\
            class C:
                def __init__(self, a: int):
                    pass

            class D:
                def __init__(self):
                    pass
            """)
        self.assertEqual((coverage.slots, coverage.annotated), (2, 1))
        self.assertEqual(coverage.typed, 1)

    def test_no_functions(self):
        """A module without functions has no percentage."""
        coverage = self.measure("X = 1\n")
        self.assertEqual(coverage.lines, 1)
        self.assertIsNone(coverage.percent)

    def test_most_typed_first(self):
        """The modules without functions last, the tests left out."""
        self.make_tree()
        lines = self.run_main(self.root)
        self.assertEqual(
            [line.split()[0] for line in lines],
            ["module", "typed.py", "half.py", "untyped.py", "empty.py"]
            + ["-" * len(lines[0]), "total"],
        )
        self.assertEqual(lines[-1].split(), ["total", "4", "3", "1", "50.0"])

    def test_by_name(self):
        """--sort name keeps the order of the paths."""
        self.make_tree()
        lines = self.run_main("--sort", "name", self.root)
        self.assertEqual(
            [line.split()[0] for line in lines[1:5]],
            ["empty.py", "half.py", "typed.py", "untyped.py"],
        )

    def test_file(self):
        """A file is named as it's given, and measured even under tests/."""
        self.make_tree()
        path = os.path.join(self.root, "tests", "test_typed.py")
        lines = self.run_main(path)
        self.assertEqual(lines[1].split(), [path, "1", "1", "0", "0.0"])

    def test_missing(self):
        """A path that isn't there is an error."""
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as raised:
                self.tool.main([self.mktemp()])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("no such file or folder", err.getvalue())
