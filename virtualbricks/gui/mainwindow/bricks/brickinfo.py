# -*- test-case-name: virtualbricks.tests.gui.mainwindow.bricks.test_brickinfo -*-
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
What the Bricks tab says about a brick, and how two bricks connect.

Nothing here builds a widget. A brick has a kind in words, "Virtual
machine" for the type "Qemu"; a summary of its settings made for the list,
"x86_64 · 512 MiB · eth0 on sw1", which the console doesn't use; a state;
and, while it runs, a process.

A brick dropped on another connects the two when one can plug into a socket
of the other: a brick with a free plug, or a virtual machine, which adds a
network card for each connection.
"""

from __future__ import annotations

import enum
import ipaddress
import itertools
import os

from virtualbricks.bricks.virtualmachine import VirtualMachine
from virtualbricks.i18n import _, ngettext
from virtualbricks.tools import is_running

# Between the parts of a summary.
SEPARATOR = " · "
QEMU_PREFIX = "qemu-system-"

# The kinds of the bricks, by their type in the code.
KINDS = {
    "Switch": _("Switch"),
    "SwitchWrapper": _("Switch wrapper"),
    "Tap": _("Tap"),
    "Wire": _("Wire"),
    "Netemu": _("Netemu"),
    "Capture": _("Capture interface"),
    "TunnelListen": _("Tunnel server"),
    "TunnelConnect": _("Tunnel client"),
    "Router": _("Router"),
    "Qemu": _("Virtual machine"),
}


class State(enum.Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    # a plug is free
    NOT_CONNECTED = "not-connected"
    # a setting it needs is missing, and it can't start
    NOT_CONFIGURED = "not-configured"


LABELS = {
    State.RUNNING: _("Running"),
    State.STOPPED: _("Stopped"),
    State.NOT_CONNECTED: _("Not connected"),
    State.NOT_CONFIGURED: _("Not configured"),
}


def kind(brick) -> str:
    """The kind of a brick, in words."""

    return KINDS.get(brick.get_type(), brick.get_type())


def state(brick) -> State:
    if is_running(brick):
        return State.RUNNING
    if not all(plug.configured() for plug in brick.plugs):
        return State.NOT_CONNECTED
    if not brick.configured():
        return State.NOT_CONFIGURED
    return State.STOPPED


def process(brick) -> int | None:
    """The process of a running brick."""

    return brick.pid if is_running(brick) else None


def summary(brick) -> str:
    """What matters about a brick, and what it is plugged into."""

    describe = _SUMMARIES.get(brick.get_type())
    if describe is None:
        return ""
    return SEPARATOR.join(describe(brick))


def _end(plug) -> str:
    return plug.sock.brick.name if plug.sock is not None else _("nothing")


def _on(plug) -> list[str]:
    if plug.sock is None:
        return []
    return [_("on {brick}").format(brick=plug.sock.brick.name)]


def _both_ways(value, back, symmetric) -> str:
    if symmetric:
        return f"{value:g}"
    return f"{value:g}/{back:g}"


def _switch(brick) -> list[str]:
    ports = brick.config.ports
    parts = [ngettext("{n} port", "{n} ports", ports).format(n=ports)]
    if brick.config.fast_spanning_tree:
        parts.append("FSTP")
    if brick.config.hub_mode:
        parts.append(_("hub"))
    return parts


def _switch_wrapper(brick) -> list[str]:
    return [brick.config.socket_path or _("no socket")]


def _tap(brick) -> list[str]:
    config = brick.config
    if config.address_mode == "manual":
        try:
            network = ipaddress.IPv4Network(f"0.0.0.0/{config.netmask}")
            address = f"{config.ip_address}/{network.prefixlen}"
        except ValueError:
            address = f"{config.ip_address}/{config.netmask}"
    elif config.address_mode == "dhcp":
        address = "DHCP"
    else:
        address = _("no address")
    return _on(brick.plugs[0]) + [address]


def _wire(brick) -> list[str]:
    return [" ↔ ".join(_end(plug) for plug in brick.plugs)]


def _netemu(brick) -> list[str]:
    config = brick.config
    parts = _wire(brick)
    if config.delay or config.delay_right_to_left:
        delay = _both_ways(
            config.delay, config.delay_right_to_left, config.delay_symmetric
        )
        parts.append(_("{delay} ms").format(delay=delay))
    if config.loss or config.loss_right_to_left:
        loss = _both_ways(
            config.loss, config.loss_right_to_left, config.loss_symmetric
        )
        parts.append(_("{loss}% loss").format(loss=loss))
    return parts


def _capture(brick) -> list[str]:
    interface = brick.config.interface or _("no interface")
    plug = brick.plugs[0]
    if plug.sock is None:
        return [interface]
    return [
        _("{interface} on {brick}").format(
            interface=interface, brick=plug.sock.brick.name
        )
    ]


def _tunnel_server(brick) -> list[str]:
    port = _("UDP port {port}").format(port=brick.config.listen_port)
    return _on(brick.plugs[0]) + [port]


def _tunnel_client(brick) -> list[str]:
    host = brick.config.server_host
    to = _("to {host}").format(host=host) if host else _("no host")
    return _on(brick.plugs[0]) + [to]


def _router(brick) -> list[str]:
    return []


def _card(brick, number, link) -> str:
    if link in brick.socks:
        return _("eth{n} as a socket").format(n=number)
    if link.sock is None:
        return _("eth{n} not connected").format(n=number)
    if getattr(link.sock, "mode", None) == "hostonly":
        return _("eth{n} host only").format(n=number)
    return _("eth{n} on {brick}").format(n=number, brick=link.sock.brick.name)


def _virtual_machine(brick) -> list[str]:
    config = brick.config
    program = os.path.basename(config.qemu_program)
    if program.startswith(QEMU_PREFIX):
        program = program[len(QEMU_PREFIX) :]
    parts = [program]
    if config.use_kvm:
        parts.append("KVM")
    parts.append(_("{size} MiB").format(size=config.memory))
    links = list(itertools.chain(brick.plugs, brick.socks))
    if not links:
        parts.append(_("no network card"))
    for number, link in enumerate(links):
        parts.append(_card(brick, number, link))
    return parts


_SUMMARIES = {
    "Switch": _switch,
    "SwitchWrapper": _switch_wrapper,
    "Tap": _tap,
    "Wire": _wire,
    "Netemu": _netemu,
    "Capture": _capture,
    "TunnelListen": _tunnel_server,
    "TunnelConnect": _tunnel_client,
    "Router": _router,
    "Qemu": _virtual_machine,
}


def _takes_plug(brick) -> bool:
    # a virtual machine adds a network card for each connection
    return isinstance(brick, VirtualMachine) or any(
        plug.sock is None for plug in brick.plugs
    )


def connection(source, destination):
    """
    How source, dropped on destination, connects to it: the brick that
    plugs in and the socket it plugs into, or None.
    """

    if destination is source:
        return None
    if source.socks and _takes_plug(destination):
        return destination, source.socks[0]
    if destination.socks and _takes_plug(source):
        return source, destination.socks[0]
    return None


def connect(source, destination) -> bool:
    """Connect source to destination, as a drop does; False if it can't."""

    found = connection(source, destination)
    if found is None:
        return False
    brick, sock = found
    brick.connect(sock)
    return True


def connectable(brick, bricks) -> list:
    """The bricks, of bricks, that brick can connect to."""

    return [other for other in bricks if connection(brick, other) is not None]
