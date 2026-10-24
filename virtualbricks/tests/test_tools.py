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
import shutil
import signal
import subprocess
import sys
import tarfile
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


def read(folder, name):
    with open(os.path.join(folder, name), encoding="utf-8") as fp:
        return fp.read()


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


# What the sdist of the containers has, its version.
VERSION = "3.0.0.dev8"
SDIST = f"virtualbricks-{VERSION}.tar.gz"


def make_sdist(folder, version, members=None):
    """An sdist in folder with a PKG-INFO of version, and members, a
    {name: text} after it."""
    path = os.path.join(folder, f"virtualbricks-{version}.tar.gz")
    files = {
        f"virtualbricks-{version}/PKG-INFO": "Metadata-Version: 2.4\n"
        f"Name: virtualbricks\nVersion: {version}\n",
        **(members or {}),
    }
    with tarfile.open(path, "w:gz") as tar:
        for name, text in files.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def git(folder, *args):
    subprocess.run(
        ["git", "-C", folder, *args], check=True, capture_output=True
    )


def make_repo(folder):
    """A Git repository of a.txt and docs/b.txt in folder."""
    os.makedirs(os.path.join(folder, "docs"))
    git(folder, "init", "-q")
    write(folder, "a.txt", "a\n")
    write(folder, "docs/b.txt", "b\n")
    git(folder, "add", ".")
    git(
        folder,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-q",
        "-m",
        "files",
    )


# A picture of Git LFS whose file the checkout has not.
LFS_POINTER = (
    "version https://git-lfs.github.com/spec/v1\n"
    "oid sha256:4d7a214614ab2935c943f9e0ff69d22eadbb8f32b1258daaa5e2ca24d17e2393\n"
    "size 12345\n"
)


class TestDebPackage(unittest.TestCase):

    def setUp(self):
        self.tool = load("debpackage")
        self.folder = os.path.abspath(self.mktemp())
        os.makedirs(self.folder)

    def debian(self, version):
        return self.tool.debian_version(version)

    def test_debian_version(self):
        """A tilde before a pre-release; the others as they are."""
        for version, debian in [
            ("3.0.0", "3.0.0"),
            ("3.0.0.dev8", "3.0.0~dev8"),
            ("3.0.0a1", "3.0.0~a1"),
            ("3.0.0b2", "3.0.0~b2"),
            ("3.0.0rc1", "3.0.0~rc1"),
            ("3.0.0rc1.dev2", "3.0.0~rc1~dev2"),
            ("3.0.0.post1", "3.0.0.post1"),
        ]:
            self.assertEqual(self.debian(version), debian)

    def test_debian_versions_in_order(self):
        """dpkg puts them in the order of Python; but a dev release after
        the alphas and the betas."""
        if shutil.which("dpkg") is None:
            raise unittest.SkipTest("dpkg")
        pairs = []
        for versions in (
            [
                "3.0.0.dev8",
                "3.0.0rc1.dev2",
                "3.0.0rc1",
                "3.0.0",
                "3.0.0.post1",
            ],
            ["3.0.0a1", "3.0.0b2", "3.0.0rc1"],
        ):
            pairs += zip(versions, versions[1:])
        for older, newer in pairs:
            subprocess.run(
                [
                    "dpkg",
                    "--compare-versions",
                    self.debian(older),
                    "lt",
                    self.debian(newer),
                ],
                check=True,
            )

    def test_sdist_version(self):
        """The PKG-INFO of the top folder, not the one of the egg-info."""
        egg = f"virtualbricks-{VERSION}/virtualbricks.egg-info/PKG-INFO"
        path = make_sdist(self.folder, VERSION, {egg: "Version: 9\n"})
        self.assertEqual(self.tool.sdist_version(path), VERSION)

    def test_sdist_without_version(self):
        path = os.path.join(self.folder, "empty.tar.gz")
        tarfile.open(path, "w:gz").close()
        self.assertRaises(ValueError, self.tool.sdist_version, path)

    def test_copy_tracked(self):
        """What Git tracks, as it is in the folder: not what it doesn't
        track, nor what is gone."""
        repo = os.path.join(self.folder, "repo")
        make_repo(repo)
        write(repo, "a.txt", "edited\n")
        write(repo, "untracked.txt", "u\n")
        os.remove(os.path.join(repo, "docs/b.txt"))
        copy = os.path.join(self.folder, "copy")
        self.tool.copy_tracked(repo, copy)
        self.assertEqual(os.listdir(copy), ["a.txt"])
        with open(os.path.join(copy, "a.txt"), encoding="utf-8") as fp:
            self.assertEqual(fp.read(), "edited\n")

    def test_lfs_pointers(self):
        """The pictures that are pointers, not the others."""
        os.makedirs(os.path.join(self.folder, "figures"))
        write(self.folder, "figures/pointer.png", LFS_POINTER)
        write(self.folder, "pointer.txt", LFS_POINTER)
        with open(os.path.join(self.folder, "picture.png"), "wb") as fp:
            fp.write(b"\x89PNG\r\n\x1a\n")
        self.assertEqual(
            self.tool.lfs_pointers(self.folder), ["figures/pointer.png"]
        )

    def test_lintian_tags(self):
        """The errors and the warnings."""
        log = (
            "running with root privileges is not recommended!\n"
            "E: virtualbricks: an-error\n"
            "W: virtualbricks source: a-warning\n"
            "I: virtualbricks: an-information\n"
            "N:   An explanation.\n"
        )
        self.assertEqual(
            self.tool.lintian_tags(log),
            [
                "E: virtualbricks: an-error",
                "W: virtualbricks source: a-warning",
            ],
        )

    def test_scripts(self):
        """The scripts of the containers are shell that sh reads."""
        tool = self.tool
        for script in (tool.SDIST, tool.BUILD, tool.INSTALL, tool.CHECK):
            subprocess.run(["sh", "-n", "-c", script], check=True)

    def test_signatures(self):
        """gpgv takes the signatures of the key; not a file changed after,
        nor one unsigned."""
        for program in ("gpg", "gpgv", "gpgconf"):
            if shutil.which(program) is None:
                raise unittest.SkipTest(program)
        # short: the sockets of gpg-agent may go in it
        home = tempfile.mkdtemp(prefix="gpg.")
        self.addCleanup(shutil.rmtree, home, True)
        old = os.environ.get("GNUPGHOME")
        os.environ["GNUPGHOME"] = home

        def restore():
            subprocess.run(["gpgconf", "--kill", "all"], check=False)
            if old is None:
                del os.environ["GNUPGHOME"]
            else:
                os.environ["GNUPGHOME"] = old

        self.addCleanup(restore)
        gpg = ["gpg", "--batch", "--quiet", "--pinentry-mode", "loopback"]
        gpg += ["--passphrase", ""]
        subprocess.run(
            gpg
            + ["--quick-gen-key", "Test <test@example.invalid>"]
            + ["ed25519", "sign", "never"],
            check=True,
            capture_output=True,
        )
        paths = {}
        for name in ("good.changes", "changed.dsc", "unsigned.buildinfo"):
            write(self.folder, f"{name}.in", f"{name}\n")
            paths[name] = os.path.join(self.folder, name)
            if name == "unsigned.buildinfo":
                os.rename(paths[name] + ".in", paths[name])
                continue
            subprocess.run(
                gpg
                + ["--clearsign", "--output", paths[name]]
                + [paths[name] + ".in"],
                check=True,
            )
        with open(paths["changed.dsc"], encoding="utf-8") as fp:
            text = fp.read()
        write(self.folder, "changed.dsc", text.replace("changed", "edited"))
        bad = self.tool.signatures(
            "test@example.invalid", list(paths.values()), self.folder
        )
        self.assertEqual(
            bad, [paths["changed.dsc"], paths["unsigned.buildinfo"]]
        )
        self.assertIn("gpgv.log", os.listdir(self.folder))

    def test_podman(self):
        """The volumes, read-only or not; sh runs the script with its
        arguments; the output in the log."""
        calls = []

        def run(command, stdout, **kwargs):
            calls.append(command)
            stdout.write("output\n")
            return subprocess.CompletedProcess(command, 3)

        self.patch(self.tool.subprocess, "run", run)
        log = os.path.join(self.folder, "log")
        Volume = self.tool.Volume
        status = self.tool.podman(
            "image",
            [Volume("/a", "/in", True), Volume("/b", "/out")],
            "script",
            ["/in/x", "y"],
            log,
        )
        self.assertEqual(status, 3)
        self.assertEqual(
            calls,
            [
                ["podman", "run", "--rm", "--volume=/a:/in:ro"]
                + ["--volume=/b:/out", "image", "sh", "-c", "script"]
                + ["sh", "/in/x", "y"]
            ],
        )
        self.assertEqual(read(self.folder, "log"), "output\n")

    def test_on_host(self):
        """A path in a volume, as the path of its folder; not the others."""
        volumes = [
            self.tool.Volume("/a", "/in"),
            self.tool.Volume("/b", "/out"),
        ]
        for arg, path in [
            ("/out", "/b"),
            ("/out/x/y", "/b/x/y"),
            ("/in/x", "/a/x"),
            ("/outside", "/outside"),
            ("3.0.0~dev8", "3.0.0~dev8"),
        ]:
            self.assertEqual(self.tool.on_host(arg, volumes), path)

    def test_in_this_system(self):
        """sh runs the script here, the volumes as their folders; the output
        in the log and on stdout."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = self.tool.in_this_system(
                [self.tool.Volume(self.folder, "/out")],
                'echo "$1" >"$2/file"; echo done; exit 3',
                ["hello", "/out"],
                os.path.join(self.folder, "log"),
            )
        self.assertEqual(status, 3)
        self.assertEqual(read(self.folder, "file"), "hello\n")
        self.assertEqual(read(self.folder, "log"), "done\n")
        self.assertEqual(out.getvalue(), "done\n")

    # main(), with fakes of the steps, debsign and gpgv

    def main(
        self,
        *argv,
        sdist=0,
        build=0,
        lintian="",
        install=0,
        programs=("podman", "debsign", "gpgv"),
        keys=("KEY",),
        signs=True,
        bad=(),
        pointer=False,
        root=False,
    ):
        """main(argv): its code, stdout, stderr and the temporary folder;
        the steps in self.calls, as (here, image, step, args), debsign in
        self.signs. sdist, build and install are the exit statuses of the
        steps, install by image if a dict; lintian is a warning it says."""
        repo = os.path.join(self.folder, "repo")
        make_repo(repo)
        if pointer:
            write(repo, "figure.png", LFS_POINTER)
            git(repo, "add", "figure.png")
        self.patch(self.tool, "ROOT", repo)
        debian = os.path.join(repo, "debian")
        os.makedirs(debian)
        write(debian, "control", "Source: virtualbricks\n")
        tmp = os.path.join(self.folder, "tmp")
        os.makedirs(tmp)
        self.patch(tempfile, "tempdir", tmp)
        self.patch(
            self.tool.shutil,
            "which",
            lambda name: f"/usr/bin/{name}" if name in programs else None,
        )
        self.patch(self.tool.os, "geteuid", lambda: 0 if root else 1000)
        self.calls = []
        self.signs = []
        steps = {
            self.tool.SDIST: "sdist",
            self.tool.BUILD: "build",
            self.tool.INSTALL: "install",
        }

        def run(here, image, volumes, script, args, log):
            folders = {volume.path: volume.host for volume in volumes}
            step = steps[script]
            self.calls.append(
                (
                    here,
                    image,
                    step,
                    [
                        "CHECK" if arg == self.tool.CHECK else arg
                        for arg in args
                    ],
                )
            )
            write(os.path.dirname(log), os.path.basename(log), "")
            if step == "sdist":
                if here:
                    self.assertEqual(folders["/src"], repo)
                else:
                    self.assertEqual(
                        sorted(os.listdir(folders["/src"])), ["a.txt", "docs"]
                    )
                if sdist == 0:
                    make_sdist(folders["/out"], VERSION)
                return sdist
            if step == "build":
                self.assertEqual(os.listdir(folders["/debian"]), ["control"])
                name = args[0].removeprefix("/sdist/")
                self.assertTrue(
                    os.path.isfile(os.path.join(folders["/sdist"], name))
                )
                out = folders["/out"]
                upstream, version = args[3:5]
                if build == 0:
                    for name in [
                        f"virtualbricks_{upstream}.orig.tar.gz",
                        f"virtualbricks_{version}.dsc",
                        f"virtualbricks_{version}.debian.tar.xz",
                        f"virtualbricks_{version}_all.deb",
                        f"virtualbricks_{version}_amd64.buildinfo",
                        f"virtualbricks_{version}_amd64.changes",
                    ]:
                        write(out, name, name)
                    write(out, "lintian.log", lintian)
                    write(out, "lintian.status", "1\n" if lintian else "0\n")
                return build
            self.assertTrue(
                any(
                    name.endswith(".deb")
                    for name in os.listdir(folders["/debs"])
                )
            )
            if isinstance(install, dict):
                return install.get(image, 0)
            return install

        def sign(key, changes, log):
            self.assertEqual(os.path.dirname(log), os.path.dirname(changes))
            self.signs.append((key, os.path.basename(changes)))
            return signs

        def signatures(key, paths, folder):
            self.assertEqual(
                [os.path.splitext(path)[1] for path in paths],
                [".changes", ".dsc", ".buildinfo"],
            )
            return [path for path in paths if path.endswith(bad)]

        self.patch(self.tool, "run", run)
        self.patch(self.tool, "sign", sign)
        self.patch(self.tool, "signatures", signatures)
        self.patch(self.tool, "has_secret_key", lambda key: key in keys)
        self.out = os.path.join(self.folder, "out")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = self.tool.main(list(argv) + ["--out", self.out])
        return code, out.getvalue().splitlines(), err.getvalue(), tmp

    def uploaded(self, *codenames):
        """The files of the uploads of codenames."""
        names = ["virtualbricks_3.0.0~dev8.orig.tar.gz"]
        for codename in codenames:
            version = f"3.0.0~dev8-0~{codename}1"
            names += [
                f"virtualbricks_{version}.debian.tar.xz",
                f"virtualbricks_{version}.dsc",
                f"virtualbricks_{version}_all.deb",
                f"virtualbricks_{version}_amd64.buildinfo",
                f"virtualbricks_{version}_amd64.changes",
            ]
        return sorted(names)

    def test_main(self):
        """The sdist, the package built, checked; in out, nothing left."""
        code, lines, err, tmp = self.main("debian-13")
        self.assertEqual(code, 0)
        trixie = "docker.io/library/debian:trixie"
        self.assertEqual(
            self.calls,
            [
                (False, trixie, "sdist", ["/src", "/out"]),
                (
                    False,
                    trixie,
                    "build",
                    [f"/sdist/{SDIST}", "/debian", "/out"]
                    + ["3.0.0~dev8", "3.0.0~dev8-0~trixie1", "trixie"],
                ),
                (False, trixie, "install", ["/debs", "CHECK"]),
            ],
        )
        self.assertEqual(
            lines,
            [
                "debian-13: virtualbricks 3.0.0~dev8-0~trixie1",
                "  lintian: nothing",
                "  the package: a switch made, the windows open",
                f"the packages: {self.out}",
            ],
        )
        self.assertEqual(err, "making the sdist\nbuilding on debian-13\n")
        self.assertEqual(sorted(os.listdir(self.out)), self.uploaded("trixie"))
        self.assertEqual(os.listdir(tmp), [])
        self.assertEqual(self.signs, [])

    def test_main_on_every_target(self):
        """One sdist; their lines in the order of TARGETS."""
        code, lines, err, tmp = self.main()
        self.assertEqual(code, 0)
        self.assertEqual(
            [step for _, _, step, _ in self.calls].count("sdist"), 1
        )
        self.assertEqual(
            [line.split(":")[0] for line in lines if line[0] != " "][:-1],
            list(self.tool.TARGETS),
        )
        codenames = [target.codename for target in self.tool.TARGETS.values()]
        self.assertEqual(
            sorted(os.listdir(self.out)), self.uploaded(*codenames)
        )

    def test_main_with_an_sdist(self):
        """No sdist made: the one given, from its folder."""
        given = os.path.join(self.folder, "given")
        os.makedirs(given)
        path = make_sdist(given, VERSION)
        code, lines, err, tmp = self.main("debian-13", "--sdist", path)
        self.assertEqual(code, 0)
        self.assertEqual(
            [step for _, _, step, _ in self.calls], ["build", "install"]
        )
        self.assertEqual(err, "building on debian-13\n")
        self.assertEqual(sorted(os.listdir(self.out)), self.uploaded("trixie"))

    def test_main_signed(self):
        """debsign signs the .changes with the key; gpgv checks."""
        code, lines, err, tmp = self.main("debian-13", "--key", "KEY")
        self.assertEqual(code, 0)
        self.assertEqual(
            self.signs,
            [("KEY", "virtualbricks_3.0.0~dev8-0~trixie1_amd64.changes")],
        )
        self.assertEqual(lines[-2], "  the signature: good, KEY")
        self.assertEqual(sorted(os.listdir(self.out)), self.uploaded("trixie"))

    def assertFailed(self, code, lines, tmp, *expected):
        """Failed: the lines of debian-13 after its first, its folder kept,
        nothing in out."""
        self.assertEqual(code, 1)
        self.assertEqual(lines[1:-1], list(expected))
        [work] = os.listdir(tmp)
        folder = os.path.join(tmp, work, "debian-13")
        self.assertEqual(lines[-1], f"  the logs: {folder}")
        self.assertTrue(os.path.isdir(folder))
        self.assertEqual(os.listdir(self.out), [])

    def test_main_with_a_bad_signature(self):
        code, lines, err, tmp = self.main(
            "debian-13", "--key", "KEY", bad=".dsc"
        )
        self.assertFailed(
            code,
            lines,
            tmp,
            "  lintian: nothing",
            "  the package: a switch made, the windows open",
            "  the signature: bad on virtualbricks_3.0.0~dev8-0~trixie1.dsc:"
            " gpgv.log",
        )

    def test_main_when_debsign_fails(self):
        code, lines, err, tmp = self.main(
            "debian-13", "--key", "KEY", signs=False
        )
        self.assertFailed(
            code,
            lines,
            tmp,
            "  lintian: nothing",
            "  the package: a switch made, the windows open",
            "  the signature: debsign failed: debsign.log",
        )

    def test_main_when_the_build_fails(self):
        """Nothing more, nothing signed."""
        code, lines, err, tmp = self.main("debian-13", "--key", "KEY", build=2)
        self.assertFailed(
            code, lines, tmp, "  the build failed (2): build.log"
        )
        self.assertEqual(
            [step for _, _, step, _ in self.calls], ["sdist", "build"]
        )
        self.assertEqual(self.signs, [])

    def test_main_when_lintian_warns(self):
        """Its tags; the package is checked all the same."""
        code, lines, err, tmp = self.main(
            "debian-13", lintian="W: virtualbricks: a-warning\n"
        )
        self.assertFailed(
            code,
            lines,
            tmp,
            "  lintian: failed: lintian.log",
            "    W: virtualbricks: a-warning",
            "  the package: a switch made, the windows open",
        )

    def test_main_when_the_package_fails(self):
        """Not installed, no switch, the windows, or the container."""
        for status, line in [
            (self.tool.NO_INSTALL, "not installed: install.log"),
            (self.tool.NO_CONSOLE, "no switch: install.log"),
            (self.tool.NO_WINDOWS, "the windows failed: install.log"),
            (125, "the container failed (125)"),
        ]:
            shutil.rmtree(self.folder)
            os.makedirs(self.folder)
            code, lines, err, tmp = self.main("debian-13", install=status)
            self.assertFailed(
                code,
                lines,
                tmp,
                "  lintian: nothing",
                f"  the package: {line}",
            )

    def test_main_when_one_fails(self):
        """The packages of the other go in out."""
        trixie = "docker.io/library/debian:trixie"
        code, lines, err, tmp = self.main(
            "debian-13",
            "ubuntu-24.04",
            install={trixie: self.tool.NO_CONSOLE},
        )
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], f"the packages that passed: {self.out}")
        self.assertEqual(sorted(os.listdir(self.out)), self.uploaded("noble"))

    def test_main_without_lfs_pictures(self):
        """No sdist."""
        code, lines, err, tmp = self.main("debian-13", pointer=True)
        self.assertEqual(code, 1)
        [work] = os.listdir(tmp)
        self.assertEqual(
            lines,
            [
                "the pictures of Git LFS are missing, as figure.png:"
                " `git lfs pull`",
                f"the logs: {os.path.join(tmp, work)}",
            ],
        )
        self.assertEqual(self.calls, [])

    def test_main_when_the_sdist_fails(self):
        code, lines, err, tmp = self.main("debian-13", sdist=1)
        self.assertEqual(code, 1)
        self.assertEqual(lines[0], "the sdist failed (1): sdist.log")
        self.assertEqual(len(self.calls), 1)

    def test_here_sdist(self):
        """Of the checkout itself, in this system; in out, the sdist."""
        code, lines, err, tmp = self.main(
            "--here", "sdist", programs=(), root=True
        )
        self.assertEqual(code, 0)
        trixie = "docker.io/library/debian:trixie"
        self.assertEqual(
            self.calls, [(True, trixie, "sdist", ["/src", "/out"])]
        )
        self.assertEqual(
            lines, [f"the sdist: {os.path.join(self.out, SDIST)}"]
        )
        self.assertEqual(os.listdir(self.out), [SDIST])
        self.assertEqual(os.listdir(tmp), [])

    def test_here_sdist_without_lfs_pictures(self):
        code, lines, err, tmp = self.main(
            "--here", "sdist", programs=(), root=True, pointer=True
        )
        self.assertEqual(code, 1)
        self.assertEqual(
            lines[0],
            "the pictures of Git LFS are missing, as figure.png:"
            " `git lfs pull`",
        )
        self.assertEqual(self.calls, [])

    def here_build(self, **kwargs):
        given = os.path.join(self.folder, "given")
        os.makedirs(given)
        path = make_sdist(given, VERSION)
        return self.main(
            "--here",
            "build",
            "--sdist",
            path,
            "ubuntu-24.04",
            programs=(),
            root=True,
            **kwargs,
        )

    def test_here_build(self):
        """The package of one distribution, in this system, from the sdist;
        not installed."""
        code, lines, err, tmp = self.here_build()
        self.assertEqual(code, 0)
        noble = "docker.io/library/ubuntu:24.04"
        self.assertEqual(
            self.calls,
            [
                (
                    True,
                    noble,
                    "build",
                    [f"/sdist/{SDIST}", "/debian", "/out"]
                    + ["3.0.0~dev8", "3.0.0~dev8-0~noble1", "noble"],
                ),
            ],
        )
        self.assertEqual(
            lines,
            [
                "ubuntu-24.04: virtualbricks 3.0.0~dev8-0~noble1",
                "  lintian: nothing",
                f"the packages: {self.out}",
            ],
        )
        self.assertEqual(sorted(os.listdir(self.out)), self.uploaded("noble"))
        self.assertEqual(os.listdir(tmp), [])

    def test_here_build_when_lintian_warns(self):
        code, lines, err, tmp = self.here_build(
            lintian="W: virtualbricks: a-warning\n"
        )
        self.assertEqual(code, 1)
        self.assertEqual(
            lines[1:3],
            [
                "  lintian: failed: lintian.log",
                "    W: virtualbricks: a-warning",
            ],
        )
        self.assertEqual(os.listdir(self.out), [])

    def test_refused(self):
        """Nothing runs."""
        missing = os.path.join(self.folder, "missing.tar.gz")
        for argv, kwargs, message in [
            (
                ["ubuntu-22.04", "debian-13"],
                {},
                "unknown distributions: ubuntu-22.04",
            ),
            (["debian-13"], {"programs": ()}, "podman isn't installed"),
            (
                ["debian-13", "--debian", self.folder],
                {},
                f"no control in {self.folder}: debian/ is on the packaging"
                " branch, gitlab-ci-dev; --debian names another folder",
            ),
            (
                ["debian-13", "--key", "KEY"],
                {"programs": ("podman", "gpgv")},
                "debsign isn't installed",
            ),
            (
                ["debian-13", "--key", "OTHER"],
                {},
                "gpg has no secret key OTHER",
            ),
            (["debian-13", "--sdist", missing], {}, f"no sdist {missing}"),
            (
                ["--here", "sdist"],
                {},
                "--here sdist installs packages: run it as root",
            ),
            (
                ["--here", "sdist", "debian-13"],
                {"root": True},
                "--here sdist takes no distribution and no --sdist",
            ),
            (
                ["--here", "build", "debian-13"],
                {"root": True},
                "--here build takes one distribution and --sdist",
            ),
            (
                ["--here", "build", "--sdist", missing]
                + ["debian-13", "ubuntu-24.04"],
                {"root": True},
                "--here build takes one distribution and --sdist",
            ),
        ]:
            shutil.rmtree(self.folder)
            os.makedirs(self.folder)
            code, lines, err, tmp = self.main(*argv, **kwargs)
            self.assertEqual((code, err), (2, message + "\n"))
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
