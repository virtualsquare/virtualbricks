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
Record what the QEMU and VDE programs of each target distribution answer.

Each target runs in a podman container: its packages are installed, its
programs are asked the questions of virtualbricks.programs, and the answers
are written to <target>.json next to this script, for the tests. Run it again
for a new distribution, or when a distribution updates its QEMU:

    python virtualbricks/tests/data/programs/record.py [TARGET...]

Without targets it records all of them. It needs podman and the network.
"""

from __future__ import annotations

import datetime
import json
import os
import shlex
import subprocess
import sys
import tempfile

from virtualbricks.programs import (
    QEMU_QUESTIONS,
    VDE_PROGRAMS,
    VDE_QUESTIONS,
    machine_question,
)

HERE = os.path.dirname(os.path.abspath(__file__))
PACKAGES = ("qemu-system-x86", "qemu-system-gui", "vde2", "vde2-cryptcab")
QEMU = "qemu-system-x86_64"
MACHINES = ("pc", "q35")
# Ubuntu moves the releases it no longer supports to old-releases: when the
# archive doesn't answer, the sources are pointed there.
OLD_RELEASES = (
    "sed -i -e 's|http://archive.ubuntu.com|http://old-releases.ubuntu.com|'"
    " -e 's|http://security.ubuntu.com|http://old-releases.ubuntu.com|'"
    " /etc/apt/sources.list.d/ubuntu.sources"
)
# The target distributions, and Ubuntu 25.04 for QEMU 9, which none of them
# ships.
TARGETS: dict[str, str] = {
    "ubuntu-22.04": "docker.io/library/ubuntu:22.04",
    "debian-12": "docker.io/library/debian:bookworm",
    "ubuntu-24.04": "docker.io/library/ubuntu:24.04",
    "ubuntu-25.04": "docker.io/library/ubuntu:25.04",
    "debian-13": "docker.io/library/debian:trixie",
    "ubuntu-26.04": "docker.io/library/ubuntu:26.04",
    "debian-testing": "docker.io/library/debian:testing",
}


def _ask(name: str, *args: str) -> str:
    return f"ask {shlex.quote(name)} {shlex.join(args)}"


def script() -> str:
    """The shell script that runs in the container, answers in /out."""

    lines = [
        "set -u",
        "export DEBIAN_FRONTEND=noninteractive LC_ALL=C",
        'ask() { name=$1; shift; if "$@" >"/out/$name.out"'
        ' 2>"/out/$name.err"; then echo 0; else echo $?; fi'
        ' >"/out/$name.status"; }',
        "apt-get update -qq >/dev/null 2>&1 ||"
        f" {{ {OLD_RELEASES} && apt-get update -qq >/dev/null; }}",
        "apt-get install -y -qq --no-install-recommends "
        f"{' '.join(PACKAGES)} >/dev/null 2>&1 || exit 1",
        "dpkg-query -W -f '${Package}\\t${Version}\\n' "
        f"{' '.join(PACKAGES)} >/out/packages.tsv",
        f"command -v {QEMU} >/out/qemu.path",
    ]
    for name, args in QEMU_QUESTIONS.items():
        lines.append(_ask(f"qemu.{name}", QEMU, *args))
    for machine in MACHINES:
        lines.append(
            _ask(f"machine.{machine}", QEMU, *machine_question(machine))
        )
    for program in VDE_PROGRAMS:
        lines.append(
            f"printf '%s\\t%s\\n' {program} \"$(command -v {program})\""
            " >>/out/vde.tsv"
        )
    for program, args in VDE_QUESTIONS.items():
        lines.append(
            f"command -v {program} >/dev/null && "
            + _ask(f"vde.{program}", program, *args)
        )
    return "\n".join(lines) + "\n"


def _read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fp:
        return fp.read()


def _answer(out: str, name: str) -> dict[str, object]:
    base = os.path.join(out, name)
    return {
        "out": _read(base + ".out"),
        "err": _read(base + ".err"),
        "status": int(_read(base + ".status")),
    }


def _table(path: str) -> dict[str, str]:
    rows = (line.split("\t", 1) for line in _read(path).splitlines())
    return {key: value for key, value in rows}


def record(target: str) -> None:
    image = TARGETS[target]
    with tempfile.TemporaryDirectory() as out:
        subprocess.run(
            ["podman", "run", "--rm", "-v", f"{out}:/out", image]
            + ["bash", "-c", script()],
            check=True,
        )
        programs = {
            name: path or None
            for name, path in _table(os.path.join(out, "vde.tsv")).items()
        }
        data = {
            "target": target,
            "image": image,
            "recorded": datetime.date.today().isoformat(),
            "packages": _table(os.path.join(out, "packages.tsv")),
            "qemu": {
                "program": _read(os.path.join(out, "qemu.path")).strip(),
                "answers": {
                    name: _answer(out, f"qemu.{name}")
                    for name in QEMU_QUESTIONS
                },
                "machines": {
                    machine: _answer(out, f"machine.{machine}")
                    for machine in MACHINES
                },
            },
            "vde": {
                "programs": programs,
                "answers": {
                    program: _answer(out, f"vde.{program}")
                    for program in VDE_QUESTIONS
                    if programs.get(program)
                },
            },
        }
    with open(os.path.join(HERE, f"{target}.json"), "w") as fp:
        json.dump(data, fp, indent=1, sort_keys=True)
        fp.write("\n")


def main(argv: list[str]) -> int:
    targets = argv or list(TARGETS)
    unknown = sorted(set(targets) - set(TARGETS))
    if unknown:
        print(f"unknown targets: {', '.join(unknown)}", file=sys.stderr)
        return 2
    for target in targets:
        print(f"recording {target}", file=sys.stderr)
        record(target)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
