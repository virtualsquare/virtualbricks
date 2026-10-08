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
A project with a brick of each kind, started with the real programs.

test_integration starts it on this machine, and
``tests/data/programs/start.py`` in the container of each target
distribution. :func:`build` makes the bricks in the open project, and
:func:`run` starts each of them, lets them run, stops them and says what
happened to each: whether it started and was still running, what it warned
about, and what its program wrote on stderr.

The machine runs paused, with QEMU's -S. The tap and the capture need root:
without it they are left out.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

from twisted.internet import defer, reactor, task
from twisted.logger import formatEvent, globalLogPublisher

from virtualbricks.bricks import must_stop, switchwrapper
from virtualbricks.bricks.eventaction import (
    ConsoleAction,
)
from virtualbricks.config.workspace import projects

# How long the bricks run before they are looked at, in seconds.
RUNNING = 2.0
# How long a brick has to stop.
STOPPING = 10.0
# The programs that each brick of the sample runs; any one of a tuple does.
PROGRAMS: dict[str, tuple[str, ...]] = {
    "sw1": ("vde_switch",),
    "sw2": ("vde_switch",),
    "sw3": ("vde_switch",),
    "vm1": ("qemu-system-x86_64",),
    "wan": ("vde-netemu", "wirefilter"),
    "w0": ("dpipe",),
    "tl0": ("vde_cryptcab",),
    "tc0": ("vde_cryptcab",),
    "wr0": (),
    "r0": ("vde_router",),
    "tap0": ("vde_plug2tap",),
    "cap0": ("vde_pcapplug",),
}
PRIVILEGED = ("tap0", "cap0")


def is_root() -> bool:
    return os.geteuid() == 0


def installed(name: str) -> bool:
    """Whether the programs of a brick of the sample are installed."""

    programs = PROGRAMS[name]
    return not programs or any(shutil.which(p) for p in programs)


def _image(folder: str, name: str, fmt: str) -> str:
    path = os.path.join(folder, f"{name}.{fmt}")
    subprocess.run(
        ["qemu-img", "create", "-q", "-f", fmt, path, "16M"], check=True
    )
    return path


def build(factory: Any, folder: str, root: bool | None = None) -> None:
    """
    Make the sample in factory: three switches, a machine on sw1 with a
    card on the host only and a socket card that a wire joins to sw3, a
    Netemu between sw1 and sw2, a tunnel from sw3 to sw2, a switch wrapper
    of sw1, a router, and with root a tap on sw2 and a capture of lo into
    sw3. When sw1 starts, an event sets the ports of sw2.

    The images of the machine's two private disks, one qcow2 and one raw,
    are made in folder.
    """

    if root is None:
        root = is_root()
    event = factory.new_event("configure")
    event.update_config({"actions": [ConsoleAction("brick set sw2 ports=8")]})
    sw1 = factory.new_brick("switch", "sw1")
    sw1.update_config({"fast_spanning_tree": True, "on_start": "configure"})
    sw2 = factory.new_brick("switch", "sw2")
    sw3 = factory.new_brick("switch", "sw3")
    factory.new_image("deb", _image(folder, "deb", "qcow2"))
    factory.new_image("raw", _image(folder, "raw", "raw"))
    vm = factory.new_brick("qemu", "vm1")
    vm.update_config(
        {
            "qemu_program": "qemu-system-x86_64",
            "headless": True,
            "use_kvm": True,
            "use_usb": True,
            "serial_socket": True,
            "sound_card": "ac97",
            "acpi": False,
            "hda_private": True,
            "hdb_private": True,
        }
    )
    vm.set_image("hda", factory.get_image("deb"))
    vm.set_image("hdb", factory.get_image("raw"))
    vm.add_plug(sw1.socks[0], "52:54:00:00:00:01", "e1000")
    vm.add_plug(factory.get_sock("_hostonly"), "52:54:00:00:00:02")
    card = vm.add_sock("52:54:00:00:00:03", "rtl8139", "lan")
    wire = factory.new_brick("wire", "w0")
    wire.plugs[0].connect(sw3.socks[0])
    wire.plugs[1].connect(card)
    wan = factory.new_brick("netemu", "wan")
    wan.plugs[0].connect(sw1.socks[0])
    wan.plugs[1].connect(sw2.socks[0])
    server = factory.new_brick("tunnellisten", "tl0")
    server.update_config({"password": "secret"})
    server.connect(sw2.socks[0])
    client = factory.new_brick("tunnelconnect", "tc0")
    client.update_config({"password": "secret", "server_host": "127.0.0.1"})
    client.connect(sw3.socks[0])
    wrapper = factory.new_brick("switchwrapper", "wr0")
    wrapper.update_config({"socket_path": sw1.path()})
    factory.new_brick("router", "r0")
    if root:
        factory.new_brick("tap", "tap0").connect(sw2.socks[0])
        capture = factory.new_brick("capture", "cap0")
        capture.update_config({"interface": "lo"})
        capture.connect(sw3.socks[0])


def _paused(command):
    def paused(prepared):
        cmd = command(prepared)
        cmd.arg("-S")
        return cmd

    return paused


class _Messages:
    """
    What the bricks and their programs log, by brick: the warnings and
    errors, what the programs write on stderr, and what both say while the
    bricks are stopped.
    """

    def __init__(self) -> None:
        self.warnings: dict[str, list[str]] = {}
        self.stderr: dict[str, list[str]] = {}
        self.stopping: dict[str, list[str]] | None = None

    def __call__(self, event: dict[str, Any]) -> None:
        source = event.get("log_source")
        brick = getattr(source, "brick", source)
        name = getattr(brick, "name", None)
        level = event.get("log_level")
        if not isinstance(name, str) or level is None:
            return
        lines = formatEvent(event).strip().splitlines()
        if event.get("stream") == "stderr":
            where = self.stderr
        elif level.name in ("warn", "error", "critical"):
            where = self.warnings
        else:
            return
        if self.stopping is not None:
            where = self.stopping
        where.setdefault(name, []).extend(lines)


def _reason(exc: BaseException) -> str:
    while isinstance(exc, defer.FirstError):
        exc = exc.subFailure.value
    return str(exc)


def _sleep(seconds: float) -> defer.Deferred:
    return task.deferLater(reactor, seconds, lambda: None)


@defer.inlineCallbacks
def _stop(brick: Any) -> Any:
    # a switch wrapper's switch stops with the switch it wraps
    if not must_stop(brick):
        return None
    if brick.get_type() == "Qemu":
        stopped = brick.stop(term=True)
    else:
        stopped = brick.stop()
    timeout = reactor.callLater(STOPPING, brick.stop, kill=True)
    try:
        _, status = yield stopped
    finally:
        if timeout.active():
            timeout.cancel()
    # a failure when the program ended well, else the reason it ended; a
    # failure returned would fail the Deferred
    return str(getattr(status, "value", status))


@defer.inlineCallbacks
def run(factory: Any) -> Any:
    """
    Start each brick of factory, one after the other, let them run, and
    stop them. Return a Deferred of a report: for each brick, whether it
    started, the error that stopped it, whether it was still running, its
    warnings and its stderr, how it ended and what it said then; and the
    ports of sw2, which the event set.
    """

    vm = factory.get_brick("vm1")
    if vm is not None:
        vm.command = _paused(vm.command)
    messages = _Messages()
    globalLogPublisher.addObserver(messages)
    report: dict[str, Any] = {"bricks": {}}
    try:
        for brick in list(factory.bricks):
            entry = report["bricks"][brick.name] = {
                "type": brick.get_type(),
                "started": False,
                "error": "",
            }
            try:
                yield brick.start()
                entry["started"] = True
            except Exception as exc:
                entry["error"] = _reason(exc)
        yield _sleep(RUNNING)
        for brick in factory.bricks:
            report["bricks"][brick.name]["running"] = brick.proc is not None
        sw2 = factory.get_brick("sw2")
        report["sw2_ports"] = sw2.config.ports if sw2 is not None else None
    finally:
        messages.stopping = {}
        # the reverse of the start: the switches last
        for brick in reversed(list(factory.bricks)):
            status = yield _stop(brick)
            if status is not None and brick.name in report["bricks"]:
                report["bricks"][brick.name]["exit"] = status
        # as Virtualbricks looks, every second: the wrapper of sw1 stops
        switchwrapper.look_all(factory)
        globalLogPublisher.removeObserver(messages)
    for name, entry in report["bricks"].items():
        entry["warnings"] = messages.warnings.get(name, [])
        entry["stderr"] = messages.stderr.get(name, [])
        entry["stopping"] = messages.stopping.get(name, [])
    return report


def private_disks(name: str = "vm1") -> list[str]:
    """The private copies that the machine's disks got, in the project."""

    folder = projects.current.path
    return sorted(f for f in os.listdir(folder) if f.startswith(f"{name}_"))
