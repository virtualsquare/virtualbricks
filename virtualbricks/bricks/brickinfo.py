# -*- test-case-name: virtualbricks.tests.bricks.test_brickinfo -*-
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
What the Bricks tab and the console say about a brick, and how two bricks
connect.

Nothing here builds a widget or loads GTK. A brick has a kind in words,
"Virtual machine" for the type "Qemu"; a summary of its settings made for
the list, "x86_64 · 512 MiB · eth0 on sw1"; a state; and, while it runs, a
process.

A brick dropped on another connects the two when one can plug into a socket
of the other: a brick with a free plug, or a virtual machine, which adds a
network card for each connection.

New Brick offers the kinds of ``NEW_KINDS``, in groups, each with a line and
a longer text. A new brick is named after its kind, ``tap1``, and the issue
of a kind is a program of its bricks that this computer lacks.
"""

from __future__ import annotations

import enum
import ipaddress
import itertools
import os
from collections.abc import Callable, Iterable, Sequence
from typing import TYPE_CHECKING, Any

import attr

from virtualbricks.bricks.capture import Capture
from virtualbricks.bricks.netemu import Netemu
from virtualbricks.bricks.plug import Plug
from virtualbricks.bricks.router import Router
from virtualbricks.bricks.sock import Sock
from virtualbricks.bricks.switch import Switch
from virtualbricks.bricks.switchwrapper import SwitchWrapper
from virtualbricks.bricks.tap import Tap
from virtualbricks.bricks.tunnelconnect import TunnelConnect
from virtualbricks.bricks.tunnellisten import TunnelListen
from virtualbricks.bricks.virtualmachine import VirtualMachine
from virtualbricks.bricks.wire import Wire
from virtualbricks.i18n import _, ngettext
from virtualbricks.programs import PACKAGES, Missing, find_program
from virtualbricks.bricks import Brick, is_running

if TYPE_CHECKING:  # pragma: no cover
    from virtualbricks.brickfactory import BrickFactory

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


def kind(brick: Brick) -> str:
    """The kind of a brick, in words."""

    return KINDS.get(brick.get_type(), brick.get_type())


def state(brick: Brick) -> State:
    if is_running(brick):
        return State.RUNNING
    if not all(plug.configured() for plug in brick.plugs):
        return State.NOT_CONNECTED
    if not brick.configured():
        return State.NOT_CONFIGURED
    return State.STOPPED


def process(brick: Brick) -> int | None:
    """
    The process of a running brick; None if it doesn't run, or for a switch
    wrapper whose switch is another user's.
    """

    return brick.pid if is_running(brick) else None


def summary(brick: Brick) -> str:
    """What matters about a brick, and what it is plugged into."""

    describe = _SUMMARIES.get(brick.get_type())
    if describe is None:
        return ""
    return SEPARATOR.join(describe(brick))


def _end(plug: Plug) -> str:
    return plug.sock.brick.name if plug.sock is not None else _("nothing")


def _on(plug: Plug) -> list[str]:
    if plug.sock is None:
        return []
    return [_("on {brick}").format(brick=plug.sock.brick.name)]


def _both_ways(value: float, back: float, symmetric: bool) -> str:
    if symmetric:
        return f"{value:g}"
    return f"{value:g}/{back:g}"


def _switch(brick: Switch) -> list[str]:
    ports = brick.config.ports
    parts = [ngettext("{n} port", "{n} ports", ports).format(n=ports)]
    if brick.config.fast_spanning_tree:
        parts.append("FSTP")
    if brick.config.hub_mode:
        parts.append(_("hub"))
    return parts


def _switch_wrapper(brick: SwitchWrapper) -> list[str]:
    return [brick.config.socket_path or _("no socket")]


def _tap(brick: Tap) -> list[str]:
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


def _wire(brick: Wire) -> list[str]:
    return [" ↔ ".join(_end(plug) for plug in brick.plugs)]


def _netemu(brick: Netemu) -> list[str]:
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


def _capture(brick: Capture) -> list[str]:
    interface = brick.config.interface or _("no interface")
    plug = brick.plugs[0]
    if plug.sock is None:
        return [interface]
    return [
        _("{interface} on {brick}").format(
            interface=interface, brick=plug.sock.brick.name
        )
    ]


def _tunnel_server(brick: TunnelListen) -> list[str]:
    port = _("UDP port {port}").format(port=brick.config.listen_port)
    return _on(brick.plugs[0]) + [port]


def _tunnel_client(brick: TunnelConnect) -> list[str]:
    host = brick.config.server_host
    to = _("to {host}").format(host=host) if host else _("no host")
    return _on(brick.plugs[0]) + [to]


def _router(brick: Router) -> list[str]:
    return []


def _card(brick: VirtualMachine, number: int, link: Plug | Sock) -> str:
    if isinstance(link, Sock):
        return _("eth{n} as a socket").format(n=number)
    if link.sock is None:
        return _("eth{n} not connected").format(n=number)
    if link.sock.mode == "hostonly":
        return _("eth{n} host only").format(n=number)
    return _("eth{n} on {brick}").format(n=number, brick=link.sock.brick.name)


def _virtual_machine(brick: VirtualMachine) -> list[str]:
    config = brick.config
    program = os.path.basename(config.qemu_program)
    if program.startswith(QEMU_PREFIX):
        program = program[len(QEMU_PREFIX) :]
    parts = [program]
    if config.use_kvm:
        parts.append("KVM")
    parts.append(_("{size} MiB").format(size=config.memory))
    links: list[Plug | Sock] = list(itertools.chain(brick.plugs, brick.socks))
    if not links:
        parts.append(_("no network card"))
    for number, link in enumerate(links):
        parts.append(_card(brick, number, link))
    return parts


# The summary of each type, which takes a brick of the type.
_SUMMARIES: dict[str, Callable[[Any], list[str]]] = {
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


def _takes_plug(brick: Brick) -> bool:
    # a virtual machine adds a network card for each connection
    return isinstance(brick, VirtualMachine) or any(
        plug.sock is None for plug in brick.plugs
    )


def connection(source: Brick, destination: Brick) -> tuple[Brick, Sock] | None:
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


def connect(source: Brick, destination: Brick) -> bool:
    """Connect source to destination, as a drop does; False if it can't."""

    found = connection(source, destination)
    if found is None:
        return False
    brick, sock = found
    brick.connect(sock)
    return True


def connectable(brick: Brick, bricks: Iterable[Brick]) -> list[Brick]:
    """The bricks, of bricks, that brick can connect to."""

    return [other for other in bricks if connection(brick, other) is not None]


# New Brick

# The kinds of brick without a control monitor: a switch wrapper's switch
# has its own, if any, which Virtualbricks doesn't know.
NO_CONSOLE = frozenset(("Tap", "Capture", "SwitchWrapper"))

# The groups of the kinds.
MACHINES = _("Machines and switches")
LINKS = _("Links")
HOST = _("This computer")


@attr.define(frozen=True)
class Kind:
    """A kind of brick, as New Brick offers it."""

    # the class of its bricks
    brick: type[Brick]
    group: str
    # one line about it, and the longer text of its tooltip
    line: str
    about: str
    # the start of the names of its bricks: "tap" for tap1
    prefix: str
    # its word in the console: brick new vm
    word: str

    @property
    def type(self) -> str:
        """The type of its bricks, as the factory takes it."""

        return self.brick.type

    @property
    def words(self) -> str:
        return KINDS[self.brick.type]


# The kinds, in the order and the groups of New Brick.
NEW_KINDS = (
    Kind(
        VirtualMachine,
        MACHINES,
        _("A computer that QEMU runs"),
        _(
            "A computer that QEMU runs, with its disks, its memory, and a"
            " network card for each switch it plugs into."
        ),
        "vm",
        "vm",
    ),
    Kind(
        Switch,
        MACHINES,
        _("The other bricks plug into its ports"),
        _(
            "A VDE switch: the other bricks plug into its ports, as into an"
            " Ethernet switch. It can start as it is."
        ),
        "sw",
        "switch",
    ),
    Kind(
        SwitchWrapper,
        MACHINES,
        _("A switch that another program runs"),
        _(
            "A switch that another program runs. The bricks of this project"
            " plug into its socket, whose path its settings give."
        ),
        "wr",
        "switchwrapper",
    ),
    Kind(
        Router,
        MACHINES,
        _("A router between switches"),
        _(
            "A VDE router between switches. It has no settings yet: its"
            " console configures it."
        ),
        "r",
        "router",
    ),
    Kind(
        Wire,
        LINKS,
        _("A cable between two switches"),
        _("A cable between two switches, which its settings choose."),
        "w",
        "wire",
    ),
    Kind(
        Netemu,
        LINKS,
        _("A cable that emulates a network link"),
        _(
            "A cable between two switches that emulates a network link: its"
            " bandwidth, delay, loss and more, in states that change over"
            " time."
        ),
        "ne",
        "netemu",
    ),
    Kind(
        TunnelListen,
        LINKS,
        _("Waits for a tunnel from another computer"),
        _(
            "One end of an encrypted tunnel: it joins a switch here to a"
            " tunnel client on another computer, which connects to it."
        ),
        "tl",
        "tunnelserver",
    ),
    Kind(
        TunnelConnect,
        LINKS,
        _("Opens a tunnel to another computer"),
        _(
            "The other end of an encrypted tunnel: it joins a switch here to"
            " a tunnel server on another computer, whose address its settings"
            " give."
        ),
        "tc",
        "tunnelclient",
    ),
    Kind(
        Tap,
        HOST,
        _("This computer, plugged into a switch"),
        _(
            "A network interface of this computer, plugged into a switch:"
            " this computer joins the lab through it. It runs as root,"
            " through sudo."
        ),
        "tap",
        "tap",
    ),
    Kind(
        Capture,
        HOST,
        _("An interface's packets, sent to a switch"),
        _(
            "An interface of this computer, whose packets go to a switch. It"
            " runs as root, through sudo."
        ),
        "cap",
        "capture",
    ),
)


def new_name(factory: BrickFactory, kind: Kind) -> str:
    """The name of a new brick of kind: its prefix and the first number free.

    Free in the whole project: no brick, event or image has the name.
    """

    names = (f"{kind.prefix}{number}" for number in itertools.count(1))
    return next(name for name in names if not factory.name_in_use(name))


@attr.define(frozen=True)
class Issue:
    """What keeps the bricks of a kind from starting on this computer."""

    # a line, and the paragraph that the tooltip starts with
    line: str
    text: str


def issue(kind: Kind, vde_folder: str, qemu_folder: str) -> Issue | None:
    """The programs of kind that this computer lacks, in words; or None."""

    lacking = [
        choice
        for choice in kind.brick.programs
        if not any(
            find_program(name, _folder(name, vde_folder, qemu_folder))
            for name in choice
        )
    ]
    if not lacking:
        return None
    line = _("{program} isn't installed").format(program=lacking[0][0])
    sentences = [_not_installed(choice) for choice in lacking]
    sentences.append(
        ngettext(
            "The brick can be made now, and starts once it is installed.",
            "The brick can be made now, and starts once they are installed.",
            len(lacking),
        )
    )
    return Issue(line, " ".join(sentences))


def _folder(name: str, vde_folder: str, qemu_folder: str) -> str:
    return qemu_folder if name.startswith("qemu-") else vde_folder


def _not_installed(choice: Sequence[str]) -> str:
    if len(choice) > 1:
        names = [str(Missing(name, PACKAGES.get(name))) for name in choice]
        return _("Neither {programs} nor {last} is installed.").format(
            programs=", ".join(names[:-1]), last=names[-1]
        )
    name = choice[0]
    package = PACKAGES.get(name)
    if package is None:
        return _(
            "{program} isn't installed, and no distribution ships it."
        ).format(program=name)
    return _(
        "{program} isn't installed: the package {package} has it."
    ).format(program=name, package=package)
