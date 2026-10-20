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
The unit tests in a container of each supported distribution, on its own
packages: its Python, GTK, PyGObject, Twisted and the programs of the bricks.

    python tools/targetsuite.py                         every distribution
    python tools/targetsuite.py ubuntu-24.04 debian-13

tox runs the tests on the Python libraries of each distribution, from PyPI,
over the C libraries of this computer (tox.ini); this runs them on all that
the distribution has, GTK, GLib and gdk-pixbuf too. Each container installs
the packages, starts the console of the sources with a switch, and runs trial
under xvfb as a user that isn't root: as root, the tests that expect a
permission error fail. The distributions run side by side.

For each it prints the versions it had, those that tox.ini has otherwise
(it and the Versions of WORKAROUNDS.md are then out of date), and the tests
that failed. The folder of a
distribution that failed stays, with the logs of apt, of the console and of
trial; the others go. The exit status is 1 if one failed. It needs podman
and the network; the sources are mounted read-only.
"""

import argparse
import configparser
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import NamedTuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOX = os.path.join(ROOT, "tox.ini")

# The supported distributions, named as the environments of tox.ini and the
# recordings of virtualbricks/tests/data/programs/ name them.
TARGETS: dict[str, str] = {
    "ubuntu-24.04": "docker.io/library/ubuntu:24.04",
    "debian-13": "docker.io/library/debian:trixie",
    "ubuntu-26.04": "docker.io/library/ubuntu:26.04",
    "debian-testing": "docker.io/library/debian:testing",
}
# Virtualbricks, and what its tests use: xvfb for the windows, the programs
# of the bricks and a terminal, openssl for the certificates, bsdtar and
# qemu-img for the archives and the disks.
PACKAGES = (
    "python3",
    "python3-twisted",
    "python3-openssl",
    "python3-service-identity",
    "python3-attr",
    "python3-tomlkit",
    "python3-markdown-it",
    "python3-pygraphviz",
    "python3-zope.interface",
    "python3-gi",
    "python3-gi-cairo",
    "gir1.2-gtk-3.0",
    "xvfb",
    "xauth",
    "vde2",
    "vde2-cryptcab",
    "qemu-system-x86",
    "qemu-utils",
    "xterm",
    "libarchive-tools",
    "openssl",
)
# The exit statuses of run.sh before the tests.
NO_UPDATE = 10
NO_PACKAGES = 11

# As root: the packages, then the tests as another user. /out stays this
# user's, for no one else to write in: the tests read their script and write
# their results in folders of their own, copied after.
RUN = f"""\
set -u
export DEBIAN_FRONTEND=noninteractive LC_ALL=C.UTF-8
apt-get update -qq >/out/apt.log 2>&1 || exit {NO_UPDATE}
apt-get install -y -qq --no-install-recommends {' '.join(PACKAGES)} \\
    >>/out/apt.log 2>&1 || exit {NO_PACKAGES}
python3 /out/versions.py /out/versions.json "$@"
useradd -m tester
cp /out/tests.sh /tmp/tests.sh
runuser -u tester -- sh /tmp/tests.sh /tmp/results
cp /tmp/results/* /out/
"""
# As the user: the console, then trial; a status file after each, in $1.
TESTS = """\
set -u
export LC_ALL=C.UTF-8 PYTHONDONTWRITEBYTECODE=1
out=$1
mkdir "$out"
cd /src
home=$(mktemp -d)
printf 'brick new switch\\nbrick list\\nquit\\n' | HOME=$home \\
    XDG_CONFIG_HOME=$home/config XDG_DATA_HOME=$home/data \\
    XDG_STATE_HOME=$home/state XDG_RUNTIME_DIR=$(mktemp -d) \\
    timeout 60 python3 -m virtualbricks --no-gui --workspace $home/workspace \\
    >"$out/console.log" 2>&1
echo $? >"$out/console.status"
xvfb-run -a timeout 1800 python3 -m twisted.trial -j4 \\
    --temp-directory "$(mktemp -d)/trial" virtualbricks >"$out/trial.log" 2>&1
echo $? >"$out/trial.status"
"""
# The versions of the Python and of the distributions named after the path.
VERSIONS = """\
import importlib.metadata
import json
import platform
import sys

found = {"Python": platform.python_version()}
for name in sys.argv[2:]:
    try:
        found[name] = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        found[name] = None
with open(sys.argv[1], "w", encoding="utf-8") as fp:
    json.dump(found, fp)
"""


class Result(NamedTuple):
    """What a distribution did: if it passed, and the lines that say it."""

    passed: bool
    lines: list[str]


def tox_pins(target: str, path: str) -> dict[str, str]:
    """The environment of target in tox.ini at path: its Python, as 3.12,
    and the version of each of its deps, name == version on each line."""

    config = configparser.ConfigParser(interpolation=None)
    config.read(path, encoding="utf-8")
    section = f"testenv:{target}"
    pins = {}
    base = config.get(section, "base_python", fallback="")
    if base:
        pins["Python"] = base.removeprefix("python")
    for line in config.get(section, "deps", fallback="").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            name, _, version = line.partition("==")
            pins[name.strip()] = version.strip()
    return pins


def differences(
    pins: dict[str, str], found: dict[str, str | None]
) -> list[str]:
    """The pins of tox that the distribution has otherwise."""

    lines = []
    for name, version in pins.items():
        here = found.get(name)
        if name == "Python":
            here = ".".join((here or "").split(".")[:2]) or None
        if here != version:
            lines.append(f"{name} {version} in tox, {here or 'none'} here")
    return lines


def failures(log: str) -> list[str]:
    """The tests that failed or had an error, in the log of trial."""

    failed: list[str] = []
    inside = False
    for line in log.splitlines():
        # the heading of each kind: [SKIPPED], [FAIL], [UNEXPECTED SUCCESS]...
        if line.startswith("[") and line.endswith("]"):
            inside = line in ("[FAIL]", "[ERROR]")
        elif inside and line.startswith("virtualbricks.") and " " not in line:
            if line not in failed:
                failed.append(line)
    return failed


def outcome(log: str) -> str:
    """The last line of trial, PASSED or FAILED with its counts."""

    for line in reversed(log.splitlines()):
        if line.startswith(("PASSED", "FAILED")):
            return line
    return ""


def _read(folder: str, name: str) -> str:
    try:
        with open(os.path.join(folder, name), encoding="utf-8") as fp:
            return fp.read()
    except FileNotFoundError:
        return ""


def summary(target: str, status: int, folder: str) -> Result:
    """What the container of target left in folder, its exit status."""

    if status == NO_UPDATE:
        return Result(False, [f"{target}: apt-get update failed: apt.log"])
    if status == NO_PACKAGES:
        return Result(False, [f"{target}: the packages failed: apt.log"])
    try:
        found = json.loads(_read(folder, "versions.json"))
    except json.JSONDecodeError:
        return Result(False, [f"{target}: the container failed ({status})"])
    lines = [
        f"{target}: "
        + ", ".join(f"{name} {version}" for name, version in found.items())
    ]
    pins = tox_pins(target, TOX)
    lines += [f"  tox: {line}" for line in differences(pins, found)]
    console = _read(folder, "console.log")
    started = _read(folder, "console.status").strip() == "0" and any(
        line.split()[:2] == ["sw1", "Switch"] for line in console.splitlines()
    )
    lines.append(
        "  the console: a switch made"
        if started
        else "  the console: no switch: console.log"
    )
    log = _read(folder, "trial.log")
    tested = _read(folder, "trial.status").strip() == "0"
    lines.append(f"  the tests: {outcome(log) or 'no result: trial.log'}")
    lines += [f"    {test}" for test in failures(log)]
    return Result(status == 0 and started and tested, lines)


def podman(image: str, folder: str, names: Sequence[str]) -> int:
    """Run run.sh of folder in a container of image: its exit status."""

    return subprocess.run(
        ["podman", "run", "--rm", "-v", f"{ROOT}:/src:ro"]
        + ["-v", f"{folder}:/out", image, "sh", "/out/run.sh", *names],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode


def check(target: str) -> Result:
    """The tests in a container of target; its folder goes if they pass."""

    folder = tempfile.mkdtemp(prefix=f"targetsuite.{target}.")
    for name, text in (
        ("run.sh", RUN),
        ("tests.sh", TESTS),
        ("versions.py", VERSIONS),
    ):
        with open(os.path.join(folder, name), "w", encoding="utf-8") as fp:
            fp.write(text)
    names = [name for name in tox_pins(target, TOX) if name != "Python"]
    status = podman(TARGETS[target], folder, names)
    result = summary(target, status, folder)
    if result.passed:
        shutil.rmtree(folder)
    else:
        result.lines.append(f"  the logs: {folder}")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="The unit tests in a container of each supported"
        " distribution, on its own packages."
    )
    parser.add_argument(
        "targets",
        nargs="*",
        metavar="DISTRIBUTION",
        help=f"{', '.join(TARGETS)} (default: all of them)",
    )
    args = parser.parse_args(argv)
    targets = args.targets or list(TARGETS)
    unknown = sorted(set(targets) - set(TARGETS))
    if unknown:
        print(f"unknown distributions: {', '.join(unknown)}", file=sys.stderr)
        return 2
    if shutil.which("podman") is None:
        print("podman isn't installed", file=sys.stderr)
        return 2
    print(f"testing on {', '.join(targets)}", file=sys.stderr)
    passed = True
    with ThreadPoolExecutor(len(targets)) as pool:
        for result in pool.map(check, targets):
            print("\n".join(result.lines), flush=True)
            passed &= result.passed
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
