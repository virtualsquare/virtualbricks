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

import configparser
import contextlib
import importlib.util
import io
import json
import os
import platform
import re
import signal
import subprocess
import sys
import tempfile
import textwrap
import tomllib

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
        """Without the windows, the console or a lock, in the folder."""
        self.assertEqual(
            self.tool.command("python3", "/run/1", False),
            [
                "python3",
                "-m",
                "virtualbricks",
                "--no-gui",
                "--no-term",
                "--lock",
                "none",
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
        # absolute, as mkdtemp() makes its folders from Python 3.12
        tmp = os.path.abspath(self.mktemp())
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


# The end of a run of trial: a test skipped, one failed, two with an error,
# one that passed though it was expected to fail.
TRIAL_LOG = """\
virtualbricks.tests.test_a
  TestA
    test_four ...                                     [UNEXPECTED SUCCESS]
    test_one ...                                                    [FAIL]
    test_two ...                                                   [ERROR]
    test_three ...                                               [SKIPPED]

===============================================================================
[SKIPPED]
pandoc

virtualbricks.tests.test_a.TestA.test_three
===============================================================================
[FAIL]
Traceback (most recent call last):
  File "/src/virtualbricks/tests/test_a.py", line 3, in test_one
    self.assertEqual(1, 2)
twisted.trial.unittest.FailTest: 1 != 2

virtualbricks.tests.test_a.TestA.test_one
===============================================================================
[ERROR]
Traceback (most recent call last):
builtins.AttributeError: module 'twisted.protocols.amp' has no attribute '_log'

virtualbricks.tests.test_a.TestA.test_two
virtualbricks.tests.test_b.TestB.test_two
===============================================================================
[UNEXPECTED SUCCESS]
virtualbricks.tests.test_a.TestA.test_four
-------------------------------------------------------------------------------
Ran 5 tests in 0.010s

FAILED (skips=1, failures=1, errors=2, unexpectedSuccesses=1, successes=0)
"""
# What the console of a container answers.
CONSOLE_LOG = """\
sw1
NAME  KIND    STATE    SUMMARY
sw1   Switch  Stopped  32 ports
"""


def write(folder, name, text):
    with open(os.path.join(folder, name), "w", encoding="utf-8") as fp:
        fp.write(text)


class TestTargetSuite(unittest.TestCase):

    def setUp(self):
        self.tool = load("targetsuite")
        self.folder = os.path.abspath(self.mktemp())
        os.makedirs(self.folder)
        # a tox.ini of the test's own
        self.patch(self.tool, "TOX", os.path.join(self.folder, "tox.ini"))
        write(
            self.folder,
            "tox.ini",
            "[testenv:debian-13]\nbase_python = python3.13\n"
            "deps =\n    Twisted==24.11.0\n",
        )
        self.out = os.path.join(self.folder, "out")
        os.makedirs(self.out)

    def test_tox_pins(self):
        """The Python as 3.12; comments aside, a version for each dep."""
        write(
            self.folder,
            "tox.ini",
            "[testenv:ubuntu-24.04]\nbase_python = python3.12\ndeps =\n"
            "    # the libraries\n    Twisted==24.3.0\n"
            "    attrs == 23.2.0  # old\n"
            "[testenv:debian-13]\nbase_python = python3.13\n",
        )
        tox = os.path.join(self.folder, "tox.ini")
        self.assertEqual(
            self.tool.tox_pins("ubuntu-24.04", tox),
            {"Python": "3.12", "Twisted": "24.3.0", "attrs": "23.2.0"},
        )
        self.assertEqual(
            self.tool.tox_pins("debian-13", tox), {"Python": "3.13"}
        )
        self.assertEqual(self.tool.tox_pins("debian-testing", tox), {})

    def test_differences(self):
        """Python by its minor version; a library missing is none."""
        pins = {"Python": "3.12", "Twisted": "24.3.0", "attrs": "23.2.0"}
        found = {"Python": "3.12.3", "Twisted": "24.3.0", "attrs": "23.2.0"}
        self.assertEqual(self.tool.differences(pins, found), [])
        found = {"Python": "3.13.5", "Twisted": "24.3.1"}
        self.assertEqual(
            self.tool.differences(pins, found),
            [
                "Python 3.12 in tox, 3.13 here",
                "Twisted 24.3.0 in tox, 24.3.1 here",
                "attrs 23.2.0 in tox, none here",
            ],
        )

    def test_failures(self):
        """Each test that failed or had an error, once; not the others."""
        self.assertEqual(
            self.tool.failures(TRIAL_LOG),
            [
                "virtualbricks.tests.test_a.TestA.test_one",
                "virtualbricks.tests.test_a.TestA.test_two",
                "virtualbricks.tests.test_b.TestB.test_two",
            ],
        )
        self.assertEqual(self.tool.failures("PASSED (successes=3)\n"), [])

    def test_outcome(self):
        self.assertEqual(
            self.tool.outcome(TRIAL_LOG),
            "FAILED (skips=1, failures=1, errors=2, unexpectedSuccesses=1,"
            " successes=0)",
        )
        self.assertEqual(self.tool.outcome(""), "")

    def test_versions(self):
        """The script of the container finds what is installed, or None."""
        import twisted

        script = os.path.join(self.folder, "versions.py")
        write(self.folder, "versions.py", self.tool.VERSIONS)
        path = os.path.join(self.out, "versions.json")
        subprocess.run(
            [sys.executable, script, path, "Twisted", "no-such-thing"],
            check=True,
        )
        with open(path, encoding="utf-8") as fp:
            self.assertEqual(
                json.load(fp),
                {
                    "Python": platform.python_version(),
                    "Twisted": twisted.__version__,
                    "no-such-thing": None,
                },
            )

    def passed(self, folder, trial="PASSED (successes=3)\n", status="0"):
        """The files of a container whose tests ran."""
        write(
            folder,
            "versions.json",
            json.dumps({"Python": "3.13.5", "Twisted": "24.11.0"}),
        )
        write(folder, "console.log", CONSOLE_LOG)
        write(folder, "console.status", "0\n")
        write(folder, "trial.log", trial)
        write(folder, "trial.status", f"{status}\n")

    def test_summary(self):
        """The versions, the console and the tests; tox has the same."""
        self.passed(self.out)
        self.assertEqual(
            self.tool.summary("debian-13", 0, self.out),
            (
                True,
                [
                    "debian-13: Python 3.13.5, Twisted 24.11.0",
                    "  the console: a switch made",
                    "  the tests: PASSED (successes=3)",
                ],
            ),
        )

    def test_summary_of_failures(self):
        """The versions that tox has otherwise; no switch; the failures."""
        self.passed(self.out, TRIAL_LOG, "1")
        write(self.out, "console.log", "Traceback\n")
        write(self.out, "console.status", "1\n")
        write(
            self.folder,
            "tox.ini",
            "[testenv:debian-13]\ndeps = Twisted==24.11.1\n",
        )
        passed, lines = self.tool.summary("debian-13", 0, self.out)
        self.assertFalse(passed)
        self.assertEqual(
            lines,
            [
                "debian-13: Python 3.13.5, Twisted 24.11.0",
                "  tox: Twisted 24.11.1 in tox, 24.11.0 here",
                "  the console: no switch: console.log",
                "  the tests: FAILED (skips=1, failures=1, errors=2,"
                " unexpectedSuccesses=1, successes=0)",
                "    virtualbricks.tests.test_a.TestA.test_one",
                "    virtualbricks.tests.test_a.TestA.test_two",
                "    virtualbricks.tests.test_b.TestB.test_two",
            ],
        )

    def test_summary_without_tests(self):
        """apt failed, or the container did."""
        self.assertEqual(
            self.tool.summary("debian-13", self.tool.NO_UPDATE, self.out),
            (False, ["debian-13: apt-get update failed: apt.log"]),
        )
        self.assertEqual(
            self.tool.summary("debian-13", self.tool.NO_PACKAGES, self.out),
            (False, ["debian-13: the packages failed: apt.log"]),
        )
        self.assertEqual(
            self.tool.summary("debian-13", 125, self.out),
            (False, ["debian-13: the container failed (125)"]),
        )

    def main(self, *argv, podman="/usr/bin/podman", trial="PASSED\n"):
        """main(argv), a fake podman: its code, stdout, stderr and calls."""
        tmp = os.path.join(self.folder, "tmp")
        os.makedirs(tmp)
        self.patch(tempfile, "tempdir", tmp)
        self.patch(self.tool.shutil, "which", lambda name: podman)
        calls = []

        def run(image, folder, names):
            calls.append((image, sorted(os.listdir(folder)), list(names)))
            self.passed(folder, trial, "0" if trial == "PASSED\n" else "1")
            return 0

        self.patch(self.tool, "podman", run)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = self.tool.main(list(argv))
        self.calls = calls
        return code, out.getvalue().splitlines(), err.getvalue(), tmp

    def test_main(self):
        """The scripts in the folder, the names of tox; nothing is left."""
        code, lines, err, tmp = self.main("debian-13")
        self.assertEqual(code, 0)
        self.assertEqual(
            self.calls,
            [
                (
                    "docker.io/library/debian:trixie",
                    ["run.sh", "tests.sh", "versions.py"],
                    ["Twisted"],
                )
            ],
        )
        self.assertEqual(
            lines,
            [
                "debian-13: Python 3.13.5, Twisted 24.11.0",
                "  the console: a switch made",
                "  the tests: PASSED",
            ],
        )
        self.assertEqual(err, "testing on debian-13\n")
        self.assertEqual(os.listdir(tmp), [])

    def test_main_when_the_tests_fail(self):
        """Its folder stays, with the logs."""
        code, lines, err, tmp = self.main("debian-13", trial=TRIAL_LOG)
        self.assertEqual(code, 1)
        [folder] = os.listdir(tmp)
        self.assertEqual(lines[-1], f"  the logs: {os.path.join(tmp, folder)}")
        self.assertIn("trial.log", os.listdir(os.path.join(tmp, folder)))

    def test_main_on_every_target(self):
        """Side by side; their lines in the order of TARGETS."""
        code, lines, err, tmp = self.main()
        self.assertEqual(
            sorted(image for image, _, _ in self.calls),
            sorted(self.tool.TARGETS.values()),
        )
        self.assertEqual(
            [line.split(":")[0] for line in lines if line[0] != " "],
            list(self.tool.TARGETS),
        )

    def test_unknown(self):
        code, lines, err, tmp = self.main("ubuntu-22.04", "debian-13")
        self.assertEqual(code, 2)
        self.assertEqual(err, "unknown distributions: ubuntu-22.04\n")
        self.assertEqual(self.calls, [])

    def test_without_podman(self):
        code, lines, err, tmp = self.main("debian-13", podman=None)
        self.assertEqual(code, 2)
        self.assertEqual(err, "podman isn't installed\n")
        self.assertEqual(self.calls, [])


def versions_table():
    """The Versions of WORKAROUNDS.md: {distribution: {row: version}}."""
    with open(os.path.join(ROOT, "WORKAROUNDS.md"), encoding="utf-8") as fp:
        section = fp.read().split("\n## Versions\n", 1)[1]
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in section.split("\n## ", 1)[0].splitlines()
        if line.startswith("|")
    ]
    header, _separator, *body = rows
    # "Debian testing, sid" is debian-testing, as tox and the recordings
    targets = [
        cell.split(",")[0].lower().replace(" ", "-") for cell in header[1:]
    ]
    return {
        target: {row[0]: row[column] for row in body}
        for column, target in enumerate(targets, 1)
    }


class TestToxVersions(unittest.TestCase):
    """The environments of tox.ini have the Versions of WORKAROUNDS.md."""

    def setUp(self):
        self.tool = load("targetsuite")
        self.versions = versions_table()

    def test_the_distributions(self):
        """The same in the table, in tox.ini and in the containers."""
        config = configparser.ConfigParser(interpolation=None)
        config.read(self.tool.TOX, encoding="utf-8")
        env_list = [
            name.strip() for name in config.get("tox", "env_list").split(",")
        ]
        sections = [
            name.removeprefix("testenv:")
            for name in config.sections()
            if name.startswith("testenv:")
        ]
        self.assertEqual(list(self.versions), list(self.tool.TARGETS))
        self.assertEqual(env_list, list(self.tool.TARGETS))
        self.assertEqual(sections, list(self.tool.TARGETS))

    def test_the_python(self):
        for target, versions in self.versions.items():
            self.assertEqual(
                self.tool.tox_pins(target, self.tool.TOX)["Python"],
                ".".join(versions["Python"].split(".")[:2]),
                target,
            )

    def test_the_libraries(self):
        """The dependencies of the package, at their versions in the table."""
        with open(os.path.join(ROOT, "pyproject.toml"), "rb") as fp:
            dependencies = tomllib.load(fp)["project"]["dependencies"]
        # Twisted[tls]>=24.3 is Twisted
        names = {re.match(r"[\w.-]+", line)[0] for line in dependencies}
        for target, versions in self.versions.items():
            pins = self.tool.tox_pins(target, self.tool.TOX)
            del pins["Python"]
            self.assertEqual(set(pins), names, target)
            self.assertEqual(
                pins, {name: versions.get(name) for name in pins}, target
            )
