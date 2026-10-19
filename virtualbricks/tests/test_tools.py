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
import signal
import sys
import tempfile
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


# Programs in place of Virtualbricks, which write their pid in their home: one
# that a SIGTERM ends, one that stays, one that never catches SIGTERM.
PID = "open(os.environ['HOME'] + '/pid', 'w').write(str(os.getpid()))\n"
LEAVES = (
    "import os, signal, time\n"
    + PID
    + "print(os.environ['HOME'], os.environ['XDG_CONFIG_HOME'],"
    " os.environ['XDG_DATA_HOME'], os.environ['XDG_RUNTIME_DIR'],"
    " flush=True)\n"
    "signal.signal(signal.SIGTERM, lambda *args: os._exit(0))\n"
    "time.sleep(30)\n"
)
STAYS = (
    "import os, signal, time\n"
    + PID
    + "signal.signal(signal.SIGTERM, lambda *args: None)\n"
    "time.sleep(30)\n"
)
DEAF = "import os, time\n" + PID + "time.sleep(30)\n"


class TestSignalRace(unittest.TestCase):

    def setUp(self):
        self.tool = load("signalrace")
        self.folder = os.path.abspath(self.mktemp())
        os.makedirs(self.folder)

    def one_run(self, code, **times):
        times.setdefault("settle", 0)
        times.setdefault("wait", 1)
        return self.tool.one_run(
            [sys.executable, "-c", code],
            self.folder,
            [signal.SIGTERM, signal.SIGTERM],
            (0, 100),
            **times,
        )

    def assertGone(self):
        with open(os.path.join(self.folder, "pid")) as file:
            pid = int(file.read())
        self.assertRaises(ProcessLookupError, os.kill, pid, 0)

    def test_command(self):
        """Without the windows or the console, in the folder."""
        self.assertEqual(
            self.tool.command("python3", "/run/1", False),
            [
                "python3",
                "-m",
                "virtualbricks",
                "--no-gui",
                "--no-term",
                "--workspace",
                "/run/1/workspace",
                "-l",
                "/run/1/vb.log",
            ],
        )
        self.assertEqual(
            self.tool.command("python3", "/run/1", True)[-2:], ["-l", "-"]
        )

    def test_a_run_that_ends(self):
        """It isn't counted; it had a home of its own."""
        self.assertIsNone(self.one_run(LEAVES))
        with open(os.path.join(self.folder, "stdout")) as file:
            self.assertEqual(
                file.read().split(),
                [
                    self.folder,
                    os.path.join(self.folder, ".config"),
                    os.path.join(self.folder, ".local", "share"),
                    os.path.join(self.folder, "run"),
                ],
            )

    def test_a_run_that_stays(self):
        """It hung; it doesn't outlive the run."""
        hung = self.one_run(STAYS)
        self.assertEqual(hung.folder, self.folder)
        self.assertGreaterEqual(hung.delay, 0)
        self.assertGone()

    def test_a_run_that_ends_first(self):
        error = self.assertRaises(
            self.tool.DidNotStart, self.one_run, "raise SystemExit(3)"
        )
        self.assertEqual(str(error), "it ended with 3")

    def test_a_run_that_never_catches_sigterm(self):
        error = self.assertRaises(
            self.tool.DidNotStart, self.one_run, DEAF, start=0.3
        )
        self.assertEqual(str(error), "it didn't catch SIGTERM in 0.3 s")
        self.assertGone()

    def main(self, *argv):
        tmp = self.mktemp()
        os.makedirs(tmp)
        self.patch(tempfile, "tempdir", tmp)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = self.tool.main(list(argv))
        return code, out.getvalue().splitlines(), tmp

    def test_main(self):
        """Two runs of this Virtualbricks; none hangs, nothing is left."""
        code, lines, tmp = self.main("--runs", "2")
        self.assertEqual(code, 0)
        self.assertEqual(
            lines, ["0 of 2 runs hung (SIGTERM SIGTERM, 200-400 µs apart)"]
        )
        self.assertEqual(os.listdir(tmp), [])

    def test_main_when_a_run_does_not_start(self):
        """The runs after it don't start; its folder stays."""
        code, lines, tmp = self.main(
            "--runs", "20", "--jobs", "1", "--python", "false"
        )
        self.assertEqual(code, 2)
        [root] = os.listdir(tmp)
        self.assertEqual(
            lines,
            [
                "A run didn't start: it ended with 1. Its folder:"
                f" {os.path.join(tmp, root, '0')}"
            ],
        )
        self.assertEqual(os.listdir(os.path.join(tmp, root)), ["0"])
