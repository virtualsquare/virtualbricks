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
Start the sample project in the container of each target distribution.

The check to run before a release, and after a distribution updates its
QEMU. Each target runs in a podman container with its own QEMU, VDE, Python
and libraries, installed from its packages, and starts the sample project of
virtualbricks.tests.sample as root, the tap and the capture included: the
project is made, saved, opened again and started. For each target it prints
what didn't start or didn't keep running, and the warnings:

    python virtualbricks/tests/data/programs/start.py [TARGET...]

Without targets it starts the project on all of them; the exit status is 1
if a brick whose programs are installed failed. It needs podman and the
network. The machine has no sound device and runs without KVM.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
PACKAGES = (
    "qemu-system-x86",
    "qemu-utils",
    "vde2",
    "vde2-cryptcab",
    "python3",
    "python3-twisted",
    "python3-attr",
    "python3-tomlkit",
)
# Needed before Python 3.11, and not packaged after.
OPTIONAL = ("python3-tomli",)
VERSIONS = ("qemu-system-x86", "vde2", "python3", "python3-twisted")
# The tap needs /dev/net/tun and the capture a raw socket.
PODMAN = (
    "--cap-add",
    "NET_ADMIN",
    "--cap-add",
    "NET_RAW",
    "--device",
    "/dev/net/tun",
)


def script() -> str:
    """The shell script that runs in the container, the report in /out."""

    # the targets and the old releases of Ubuntu, as the recordings have them
    sys.path.insert(0, HERE)
    from record import OLD_RELEASES

    optional = " ".join(
        f"$(apt-cache show {name} >/dev/null 2>&1 && echo {name})"
        for name in OPTIONAL
    )
    return (
        "\n".join(
            [
                "set -u",
                "export DEBIAN_FRONTEND=noninteractive LC_ALL=C",
                "apt-get update -qq >/dev/null 2>&1 ||"
                f" {{ {OLD_RELEASES} && apt-get update -qq >/dev/null; }}",
                "apt-get install -y -qq --no-install-recommends"
                f" {' '.join(PACKAGES)} {optional} >/dev/null 2>&1 || exit 1",
                "dpkg-query -W -f '${Package}\\t${Version}\\n' "
                f"{' '.join(VERSIONS)} >/out/packages.tsv",
                "cd /src && PYTHONPATH=/src PYTHONDONTWRITEBYTECODE=1"
                " python3 virtualbricks/tests/data/programs/start.py"
                " --inside /out/report.json",
            ]
        )
        + "\n"
    )


def inside(path: str) -> int:
    """Start the sample here, as root, and write its report to path."""

    root = tempfile.mkdtemp(prefix="vb-")
    os.environ.update(
        HOME=root,
        XDG_CONFIG_HOME=os.path.join(root, "config"),
        XDG_STATE_HOME=os.path.join(root, "state"),
        XDG_RUNTIME_DIR=os.path.join(root, "run"),
    )
    import attr
    import tomlkit
    import twisted
    from twisted.internet import defer, reactor

    from virtualbricks.brickfactory import BrickFactory
    from virtualbricks.config.settings import set_setting
    from virtualbricks.config.workspace import projects
    from virtualbricks.tests import sample

    result: dict = {}

    @defer.inlineCallbacks
    def start():
        set_setting("audio_driver", "none")
        projects._path = os.path.join(root, "workspace")
        os.makedirs(projects._path)
        factory = BrickFactory(defer.Deferred())
        projects.create("sample")
        projects.open("sample", factory)
        sample.build(factory, projects.current.path)
        projects.save(factory)
        projects.close(factory)
        reopened = projects.open("sample", factory)
        report = yield sample.run(factory)
        for name, entry in report["bricks"].items():
            entry["installed"] = sample.installed(name)
        report["reopened"] = [str(message) for message in reopened]
        report["private_disks"] = sample.private_disks()
        report["python"] = sys.version.split()[0]
        report["twisted"] = twisted.__version__
        report["attrs"] = attr.__version__
        report["tomlkit"] = tomlkit.__version__
        result.update(report)

    def stop(outcome):
        if outcome is not None:
            result["failure"] = outcome.getTraceback()
        reactor.stop()

    reactor.callWhenRunning(lambda: start().addBoth(stop))
    reactor.run()
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(result, fp, indent=1)
    return 0


def _table(path: str) -> dict[str, str]:
    with open(path, encoding="utf-8") as fp:
        rows = (line.split("\t", 1) for line in fp.read().splitlines())
        return {key: value for key, value in rows}


def problems(report: dict) -> list[str]:
    """The bricks whose programs are installed but didn't start or run."""

    found = []
    for name, entry in report.get("bricks", {}).items():
        if entry["installed"] and (entry["error"] or not entry["running"]):
            found.append(name)
    if report.get("sw2_ports") != 8:
        found.append("the event of sw1")
    if len(report.get("private_disks", ())) != 2:
        found.append("the private disks of vm1")
    if report.get("reopened") or "failure" in report:
        found.append("the project")
    return found


def summary(target: str, report: dict, packages: dict[str, str]) -> str:
    lines = [
        f"{target}: QEMU {packages.get('qemu-system-x86', '?')},"
        f" vde2 {packages.get('vde2', '?')},"
        f" Python {report.get('python', '?')},"
        f" Twisted {report.get('twisted', '?')},"
        f" attrs {report.get('attrs', '?')},"
        f" tomlkit {report.get('tomlkit', '?')}"
    ]
    if "failure" in report:
        lines.append(report["failure"])
    for message in report.get("reopened", ()):
        lines.append(f"  reopened: {message}")
    for name, entry in report.get("bricks", {}).items():
        if entry["error"]:
            state = f"didn't start: {entry['error']}"
        elif not entry["running"]:
            state = "stopped by itself"
        else:
            state = "running"
        if not entry["installed"]:
            state += " (its program isn't packaged)"
        lines.append(f"  {name} ({entry['type']}): {state}")
        for warning in entry["warnings"]:
            lines.append(f"    warning: {warning}")
        if entry["error"] or not entry["running"]:
            for line in entry["stderr"]:
                lines.append(f"    stderr: {line}")
    lines.append(
        f"  the event set the ports of sw2 to {report.get('sw2_ports')}"
    )
    lines.append(
        f"  private disks: {', '.join(report.get('private_disks', ()))}"
    )
    found = problems(report)
    lines.append(
        f"  problems: {', '.join(found)}" if found else "  no problems"
    )
    return "\n".join(lines)


def start(target: str, image: str) -> list[str]:
    with tempfile.TemporaryDirectory() as out:
        run = subprocess.run(
            ["podman", "run", "--rm", *PODMAN]
            + ["-v", f"{SOURCE}:/src:ro", "-v", f"{out}:/out", image]
            + ["bash", "-c", script()],
        )
        path = os.path.join(out, "report.json")
        if run.returncode != 0 or not os.path.exists(path):
            print(f"{target}: the container failed ({run.returncode})")
            return ["the container"]
        with open(path, encoding="utf-8") as fp:
            report = json.load(fp)
        packages = _table(os.path.join(out, "packages.tsv"))
    print(summary(target, report, packages), flush=True)
    return problems(report)


def main(argv: list[str]) -> int:
    if argv[:1] == ["--inside"]:
        return inside(argv[1])
    sys.path.insert(0, HERE)
    from record import TARGETS

    targets = argv or list(TARGETS)
    unknown = sorted(set(targets) - set(TARGETS))
    if unknown:
        print(f"unknown targets: {', '.join(unknown)}", file=sys.stderr)
        return 2
    failed = False
    for target in targets:
        print(f"starting the sample on {target}", file=sys.stderr)
        failed |= bool(start(target, TARGETS[target]))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
