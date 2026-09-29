# -*- test-case-name: virtualbricks.tests.console.test_bricks -*-
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
The commands of the bricks: brick list, new, set, start, and the rest.

They do what the Bricks tab does, with its words: a setting is set through
the brick's draft, with the checks of its panel; the kinds are those of New
Brick; a running brick can't be renamed, deleted or plugged elsewhere.
"""

from __future__ import annotations

import signal

from twisted.internet import defer, error
from twisted.logger import Logger
from twisted.python.failure import Failure

from virtualbricks import bricks as bricks_module
from virtualbricks import errors
from virtualbricks.bricks import brickinfo
from virtualbricks.bricks.brickinfo import (
    LABELS,
    NEW_KINDS,
    NO_CONSOLE,
    issue,
    new_name,
)
from virtualbricks.bricks.draft import apply
from virtualbricks.bricks.virtualmachine import (
    hostonly_sock,
    is_virtualmachine,
    resume as resume_vm,
    suspend as suspend_vm,
)
from virtualbricks.config.schema import (
    field_default,
    field_help,
    field_names,
    field_values,
    kind_of,
    parse_value,
    why_unused,
)
from virtualbricks.config.settings import get_setting
from virtualbricks.console.command import (
    Arg,
    ArgKind,
    Choice,
    CommandError,
    KeyValues,
    Named,
    Text,
    command,
)
from virtualbricks.console.output import table
from virtualbricks.i18n import N_, _
from virtualbricks.tools import is_running

logger = Logger()
start_failed = "Starting {name} failed"
stop_failed = "Stopping {name} failed"


# The arguments


def _bricks(factory):
    return [brick.name for brick in factory.bricks]


BRICK = Named(
    lambda factory, name: factory.get_brick_by_name(name),
    _bricks,
    N_("No brick named {name}"),
)


class VirtualMachineArg(Named):
    """The name of a virtual machine of the project."""

    def __init__(self):
        super().__init__(
            lambda factory, name: factory.get_brick_by_name(name),
            lambda factory: [
                b.name for b in factory.bricks if is_virtualmachine(b)
            ],
            N_("No brick named {name}"),
        )

    def read(self, context, word):
        brick = super().read(context, word)
        if not is_virtualmachine(brick):
            raise CommandError(
                _("{name} is not a virtual machine").format(name=word)
            )
        return brick


VM = VirtualMachineArg()


def _find_kind(word):
    for kind in NEW_KINDS:
        if word.lower() in (kind.word, kind.type.lower()):
            return kind
    return None


class KindArg(ArgKind):
    """A kind of brick: its word, as vm, or its type, as qemu."""

    def read(self, context, word):
        kind = _find_kind(word)
        if kind is None:
            raise CommandError(
                _("No kind {word}: brick types lists them").format(word=word)
            )
        return kind

    def candidates(self, context, done):
        return [kind.word for kind in NEW_KINDS]


class KindOrBrick(ArgKind):
    """A brick of the project, or else a kind of brick."""

    def read(self, context, word):
        brick = context.factory.get_brick_by_name(word)
        if brick is not None:
            return brick
        return KindArg().read(context, word)

    def candidates(self, context, done):
        return _bricks(context.factory) + KindArg().candidates(context, done)


def _socket_name(sock):
    """How a socket is named in the console: its brick, or vm:name."""

    brick = sock.brick
    if is_virtualmachine(brick):
        return f"{brick.name}:{sock.nickname[len(brick.name) + 1:]}"
    return brick.name


class Target(ArgKind):
    """A socket to plug into: a brick with one, as sw1, or vm1:sock_eth1."""

    def read(self, context, word):
        factory = context.factory
        for sock in factory.socks:
            if sock.brick is not None and _socket_name(sock) == word:
                return sock
        brick = factory.get_brick_by_name(word)
        if brick is None:
            raise CommandError(_("No brick named {name}").format(name=word))
        raise CommandError(
            _("{name} has no socket to plug into").format(name=word)
        )

    def candidates(self, context, done):
        return sorted(
            {
                _socket_name(sock)
                for sock in context.factory.socks
                if sock.brick is not None
            }
        )


class CardArg(ArgKind):
    """A network card of a machine, as its summary names it: eth0."""

    def read(self, context, word):
        if word.startswith("eth") and word[3:].isdigit():
            return int(word[3:])
        raise CommandError(
            _('"{word}" is not a card: eth0, eth1…').format(word=word)
        )

    def candidates(self, context, done):
        vm = done.get("vm")
        if vm is None:
            return []
        return [f"eth{n}" for n in range(len(vm.plugs) + len(vm.socks))]


def _config(done):
    brick = done.get("name")
    return None if brick is None else brick.config


def _kind_of_key(config, key):
    try:
        return kind_of(config, key)
    except KeyError:
        return None


# KEY=VALUE, with the keys of the brick named before
BRICK_KEYS = KeyValues(
    lambda context, done: (
        field_names(_config(done)) if _config(done) is not None else []
    ),
    lambda context, done, key: (
        _kind_of_key(_config(done), key) if _config(done) is not None else None
    ),
)


class BrickKey(ArgKind):
    """A key of the brick named before."""

    def candidates(self, context, done):
        config = _config(done)
        return [] if config is None else field_names(config)


# What the commands share


def _stopped(brick):
    if is_running(brick):
        raise CommandError(
            _("{name} is running: stop it first").format(name=brick.name)
        )


def _key_error(brick, key):
    return CommandError(
        _("{name} has no key {key}: brick keys {name} lists them").format(
            name=brick.name, key=key
        )
    )


def _problem(brick, problem):
    return f"{brick.name} {problem.key}: {problem.text}"


def _give(brick, draft, changed):
    """Apply draft, and say what the brick keeps for later."""

    errors_ = draft.errors()
    if errors_:
        raise CommandError(_problem(brick, errors_[0]))
    apply(draft)
    lines = [
        _problem(brick, problem)
        for problem in draft.problems()
        if not problem.error and problem.key in changed
    ]
    if is_running(brick):
        waiting = [name for name in changed if name not in draft.live()]
        if waiting:
            lines.append(
                _(
                    "{name} is running: {keys} count from its next start"
                ).format(name=brick.name, keys=", ".join(waiting))
            )
    return lines


def _set(brick, values):
    """Set the keys of values, a dict of key and value, all or none."""

    draft = brick.draft_factory(brick)
    names = field_names(draft.settings)
    for key, value in values.items():
        if key not in names:
            raise _key_error(brick, key)
        draft.set(key, value)
    changed = [key for key in values if key in draft.changes()]
    return _give(brick, draft, changed)


def _card_line(brick, number, link):
    if link in brick.socks:
        where = _("socket {name}").format(name=_socket_name(link))
    elif link.sock is None:
        where = _("in nothing")
    elif link.sock is hostonly_sock:
        where = _("host only")
    else:
        where = _("plugged into {name}").format(name=_socket_name(link.sock))
    return f"eth{number}: {where}, {link.model}, {link.mac}"


def _links(brick):
    """The lines of a brick's links: its cards, ends or plug."""

    if is_virtualmachine(brick):
        links = list(brick.plugs) + list(brick.socks)
        return [_card_line(brick, n, link) for n, link in enumerate(links)]
    lines = []
    ends = (_("left"), _("right")) if len(brick.plugs) == 2 else None
    for index, plug in enumerate(brick.plugs):
        into = (
            _socket_name(plug.sock) if plug.sock is not None else _("nothing")
        )
        if ends is None:
            lines.append(_("plugged into {name}").format(name=into))
        else:
            lines.append(f"{ends[index]}: {into}")
    return lines


# The commands


@command(
    "brick",
    "types",
    help=N_("The kinds of brick, and what this computer lacks for each"),
)
def types(context):
    rows = []
    vde, qemu = get_setting("vde_path"), get_setting("qemu_path")
    for kind in NEW_KINDS:
        found = issue(kind, vde, qemu)
        rows.append(
            (kind.word, kind.words, found.line if found else kind.line)
        )
    return table(rows, [_("KIND"), _("NAME"), _("WHAT IT IS")])


@command("brick", "list", help=N_("The bricks, their state and settings"))
def list_(context):
    bricks = list(context.factory.bricks)
    if not bricks:
        return [_("No bricks")]
    rows = [
        (
            brick.name,
            brickinfo.kind(brick),
            LABELS[brickinfo.state(brick)],
            brickinfo.summary(brick),
        )
        for brick in bricks
    ]
    return table(rows, [_("NAME"), _("KIND"), _("STATE"), _("SUMMARY")])


@command(
    "brick",
    "new",
    Arg("KIND", KindArg()),
    Arg("NAME", optional=True),
    help=N_(
        "Make a brick; without a name, the kind's and the first free number"
    ),
    example="brick new switch",
)
def new(context, kind, name):
    factory = context.factory
    if name is None:
        name = new_name(factory, kind)
    else:
        name = factory.check_name(kind.type, name)
    factory.new_brick(kind.type, name)
    lines = [name]
    found = issue(kind, get_setting("vde_path"), get_setting("qemu_path"))
    if found is not None:
        lines.append(found.line)
    return lines


@command(
    "brick",
    "show",
    Arg("NAME", BRICK),
    help=N_("A brick's state, links and keys"),
)
def show(context, name):
    brick = name
    head = [brick.name, brickinfo.kind(brick), LABELS[brickinfo.state(brick)]]
    process = brickinfo.process(brick)
    if process is not None:
        head.append(_("process {pid}").format(pid=process))
    lines = ["  ".join(head)] + _links(brick)
    for key, value in field_values(brick.config).items():
        line = f"{key} = {kind_of(brick.config, key).format(value)}"
        other = why_unused(brick.config, key)
        if other is not None:
            now = kind_of(brick.config, other).format(
                getattr(brick.config, other)
            )
            line += "  # " + _("not used: {key} is {value}").format(
                key=other, value=now
            )
        lines.append(line)
    return lines


@command(
    "brick",
    "keys",
    Arg("KIND|NAME", KindOrBrick()),
    Arg("KEY", optional=True),
    help=N_(
        "The keys of a kind of brick or of a brick, or one, with what each"
        " is for"
    ),
    example="brick keys vm memory",
)
def keys(context, kind_name, key):
    if isinstance(kind_name, brickinfo.Kind):
        config = kind_name.brick.config_factory
    else:
        config = kind_name.config

    def described(name):
        help, detail = field_help(config, name)
        text = _(help) if help else ""
        return f"{text} ({detail})" if detail else text

    if key is not None:
        try:
            return [f"{key}: {described(key)}"]
        except KeyError:
            raise CommandError(
                _("No key {key}: brick keys lists them").format(key=key)
            ) from None
    return table([(name, described(name)) for name in field_names(config)])


@command(
    "brick",
    "set",
    Arg("NAME", BRICK),
    Arg("KEY=VALUE", BRICK_KEYS, many=True),
    help=N_("Change keys of a brick, all or none"),
    example="brick set sw1 ports=16 hub_mode=true",
)
def set_(context, name, key_value):
    brick = name
    values = {}
    for key, text in key_value:
        try:
            values[key] = parse_value(brick.config, key, text)
        except KeyError:
            raise _key_error(brick, key) from None
        except ValueError as exc:
            reason = str(exc).removeprefix(f"{key}: ")
            raise CommandError(f"{brick.name} {key}: {reason}") from None
    return _set(brick, values)


@command(
    "brick",
    "unset",
    Arg("NAME", BRICK),
    Arg("KEY", BrickKey(), many=True),
    help=N_("Put keys of a brick back to their defaults"),
    example="brick unset sw1 ports",
)
def unset(context, name, key):
    brick = name
    values = {}
    for each in key:
        try:
            values[each] = field_default(brick.config, each)
        except KeyError:
            raise _key_error(brick, each) from None
    return _set(brick, values)


def _message(failure):
    return failure.getErrorMessage() or failure.type.__name__


def _started(factory, before):
    return [
        _("{name} runs, process {pid}").format(name=b.name, pid=b.pid)
        for b in factory.bricks
        if is_running(b) and b not in before
    ]


@command(
    "brick",
    "start",
    Arg("NAME", BRICK, many=True),
    help=N_("Start bricks, after those they plug into, and wait for them"),
    example="brick start router",
)
@defer.inlineCallbacks
def start(context, name):
    factory = context.factory
    before = {b for b in factory.bricks if is_running(b)}
    lines = [
        _("{name} runs already").format(name=b.name)
        for b in name
        if b in before
    ]
    for brick in name:
        try:
            yield brick.poweron()
        except Exception:
            failure = Failure()
            if not failure.check(errors.Error):
                logger.failure(start_failed, failure, name=brick.name)
            raise CommandError(
                _message(failure), lines + _started(factory, before)
            ) from None
    return lines + _started(factory, before)


@defer.inlineCallbacks
def _stop(context, bricks, kill):
    lines = []
    for brick in bricks:
        if not is_running(brick):
            lines.append(_("{name} isn't running").format(name=brick.name))
            continue
        try:
            yield brick.poweroff(kill=kill)
        except Exception:
            failure = Failure()
            logger.failure(stop_failed, failure, name=brick.name)
            raise CommandError(
                f"{brick.name}: {_message(failure)}", lines
            ) from None
        lines.append(_("{name} stopped").format(name=brick.name))
    return lines


@command(
    "brick",
    "stop",
    Arg("NAME", BRICK, many=True),
    help=N_("Stop bricks, and wait until their programs end"),
)
def stop(context, name):
    return _stop(context, name, kill=False)


@command(
    "brick",
    "kill",
    Arg("NAME", BRICK, many=True),
    help=N_("Kill the programs of bricks"),
)
def kill(context, name):
    return _stop(context, name, kill=True)


def _running(brick):
    if not is_running(brick):
        raise CommandError(_("{name} isn't running").format(name=brick.name))


@command(
    "brick",
    "restart",
    Arg("NAME", BRICK, many=True),
    help=N_("Stop bricks, killing them after two seconds, and start them"),
)
@defer.inlineCallbacks
def restart(context, name):
    for brick in name:
        _running(brick)
    lines = []
    for brick in name:
        try:
            yield bricks_module.restart(brick, context.reactor)
        except Exception:
            failure = Failure()
            raise CommandError(
                f"{brick.name}: {_message(failure)}", lines
            ) from None
        lines.append(
            _("{name} runs again, process {pid}").format(
                name=brick.name, pid=brick.pid
            )
        )
    return lines


def _signal(bricks, number):
    for brick in bricks:
        _running(brick)
    for brick in bricks:
        try:
            brick.send_signal(number)
        except error.ProcessExitedAlready:
            pass


@command(
    "brick",
    "pause",
    Arg("NAME", BRICK, many=True),
    help=N_("Pause the programs of bricks"),
)
def pause(context, name):
    _signal(name, signal.SIGSTOP)


@command(
    "brick",
    "continue",
    Arg("NAME", BRICK, many=True),
    help=N_("Let paused bricks go on"),
)
def continue_(context, name):
    _signal(name, signal.SIGCONT)


@command(
    "brick",
    "suspend",
    Arg("VM", VM),
    help=N_("Save a machine's state in its first disk, and stop it"),
)
@defer.inlineCallbacks
def suspend(context, vm):
    _running(vm)
    yield suspend_vm(vm)
    return [_("{name} is suspended").format(name=vm.name)]


@command(
    "brick",
    "resume",
    Arg("VM", VM),
    help=N_("Start a machine from the state that suspend saved"),
)
@defer.inlineCallbacks
def resume(context, vm):
    yield resume_vm(vm)
    return [_("{name} is resumed").format(name=vm.name)]


@command(
    "brick",
    "reset",
    Arg("VM", VM),
    help=N_("Reset a running machine, as its reset button"),
)
def reset(context, vm):
    _running(vm)
    vm.send(b"system_reset\n")


@command(
    "brick",
    "monitor",
    Arg("NAME", BRICK),
    help=N_("Open the control monitor of a running brick in a terminal"),
)
def monitor(context, name):
    brick = name
    if brick.get_type() in NO_CONSOLE:
        raise CommandError(
            _("{name} has no control monitor").format(name=brick.name)
        )
    _running(brick)
    brick.open_console()


def _plugs(brick):
    """The plugs of a brick that isn't a machine, which cards replace."""

    if is_virtualmachine(brick):
        raise CommandError(
            _(
                "{name} has network cards: brick card add {name} plug TARGET"
            ).format(name=brick.name)
        )
    if not brick.plugs:
        raise CommandError(
            _("{name} doesn't plug into anything").format(name=brick.name)
        )


@command(
    "brick",
    "connect",
    Arg("NAME", BRICK),
    Arg("TARGET", Target(), many=True),
    help=N_(
        "Plug a brick into switches: a wire or a Netemu's ends, left then"
        " right"
    ),
    example="brick connect w1 sw1 sw2",
)
def connect(context, name, target):
    brick = name
    _plugs(brick)
    _stopped(brick)
    draft = brick.draft_factory(brick)
    if len(target) > len(brick.plugs):
        raise CommandError(
            _("{name} has {count} plugs").format(
                name=brick.name, count=len(brick.plugs)
            )
        )
    if len(target) == len(brick.plugs):
        indexes = list(range(len(target)))
    else:
        indexes = [i for i, sock in enumerate(draft.links) if sock is None]
        if len(indexes) < len(target):
            raise CommandError(
                _("{name} has no free plug: brick disconnect {name}").format(
                    name=brick.name
                )
            )
    allowed = draft.sockets()
    for index, sock in zip(indexes, target):
        if sock not in allowed:
            raise CommandError(
                _(
                    "{brick} can't plug into {target}: only switches take"
                    " plugs, unless allow_female_plugs is true"
                ).format(brick=brick.name, target=_socket_name(sock))
            )
        draft.link(index, sock)
    apply(draft)
    return _links(brick)


@command(
    "brick",
    "disconnect",
    Arg("NAME", BRICK),
    Arg("END", Choice("left", "right"), optional=True),
    help=N_("Unplug a brick, or one end of a wire or a Netemu"),
)
def disconnect(context, name, end):
    brick = name
    _plugs(brick)
    _stopped(brick)
    draft = brick.draft_factory(brick)
    if end is None:
        indexes = range(len(brick.plugs))
    elif len(brick.plugs) != 2:
        raise CommandError(
            _("{name} has no ends: brick disconnect {name}").format(
                name=brick.name
            )
        )
    else:
        indexes = [0 if end == "left" else 1]
    for index in indexes:
        draft.link(index, None)
    apply(draft)
    return _links(brick)


# The network cards of a machine


def _card_values(context, vm, words, target_allowed):
    """The target and the model and mac of the words of a card command."""

    values = {}
    for word in words:
        key, sep, value = word.partition("=")
        if sep and key in ("model", "mac"):
            values[key] = value
        elif sep and key == "target" and target_allowed:
            values["sock"] = _card_sock(context, value)
        elif not sep and target_allowed and "sock" not in values:
            values["sock"] = _card_sock(context, word)
        else:
            raise CommandError(
                _('"{word}" is not model=, mac= or a target').format(word=word)
            )
    return values


def _card_sock(context, word):
    if word == "":
        return None
    if word == "hostonly":
        return hostonly_sock
    return Target().read(context, word)


def _check_cards(vm, draft):
    for problem in draft.errors():
        if problem.key.startswith("card"):
            number = problem.key[len("card") :]
            raise CommandError(f"{vm.name} eth{number}: {problem.text}")
        raise CommandError(_problem(vm, problem))


def _card_index(vm, number):
    count = len(vm.plugs) + len(vm.socks)
    if number >= count:
        raise CommandError(
            _("{name} has no eth{number}").format(name=vm.name, number=number)
        )
    return number


@command(
    "brick",
    "card add",
    Arg("VM", VM),
    Arg("KIND", Choice("plug", "socket", "hostonly")),
    Arg("OPTIONS", Text(), many=True, optional=True),
    help=N_(
        "Add a network card: plugged into TARGET, a socket, or host only;"
        " model= and mac= are its own"
    ),
    example="brick card add vm1 plug sw1 model=virtio-net-pci",
)
def card_add(context, vm, kind, options):
    _stopped(vm)
    values = _card_values(context, vm, options, kind == "plug")
    if kind == "hostonly":
        values["sock"] = hostonly_sock
    draft = vm.draft_factory(vm)
    index = draft.add_card()
    if kind == "socket":
        values["kind"] = "socket"
    draft.set_card(index, **values)
    _check_cards(vm, draft)
    before = {id(link) for link in list(vm.plugs) + list(vm.socks)}
    apply(draft)
    links = list(vm.plugs) + list(vm.socks)
    for number, link in enumerate(links):
        if id(link) not in before:
            return [f"{vm.name} {_card_line(vm, number, link)}"]
    return []


@command(
    "brick",
    "card set",
    Arg("VM", VM),
    Arg("CARD", CardArg()),
    Arg(
        "KEY=VALUE",
        KeyValues(
            lambda context, done: ["model", "mac", "target"],
            lambda context, done, key: None,
        ),
        many=True,
    ),
    help=N_(
        "Change a card's model, mac, or target: a switch, hostonly, or"
        " nothing"
    ),
    example="brick card set vm1 eth0 model=e1000 target=sw2",
)
def card_set(context, vm, card, key_value):
    _stopped(vm)
    index = _card_index(vm, card)
    draft = vm.draft_factory(vm)
    is_plug = draft.cards[index].kind == "plug"
    words = [f"{key}={value}" for key, value in key_value]
    values = _card_values(context, vm, words, is_plug)
    draft.set_card(index, **values)
    _check_cards(vm, draft)
    apply(draft)
    links = list(vm.plugs) + list(vm.socks)
    return [f"{vm.name} {_card_line(vm, index, links[index])}"]


@command(
    "brick",
    "card remove",
    Arg("VM", VM),
    Arg("CARD", CardArg(), many=True),
    help=N_("Take network cards out of a machine"),
)
def card_remove(context, vm, card):
    _stopped(vm)
    draft = vm.draft_factory(vm)
    for index in sorted({_card_index(vm, n) for n in card}, reverse=True):
        draft.remove_card(index)
    apply(draft)
    return _links(vm)


@command(
    "brick",
    "rename",
    Arg("NAME", BRICK),
    Arg("NEW"),
    help=N_("Rename a brick"),
)
def rename(context, name, new):
    brick = name
    _stopped(brick)
    factory = context.factory
    final = factory.check_name(brick.get_type(), new)
    factory.rename(brick, final)
    return [final] if final != new else []


@command(
    "brick",
    "duplicate",
    Arg("NAME", BRICK),
    Arg("NEW", optional=True),
    help=N_("Copy a brick, with its links"),
)
def duplicate(context, name, new):
    factory = context.factory
    if new is not None:
        new = factory.check_name(name.get_type(), new)
    copy = factory.dup_brick(name)
    if new is not None:
        factory.rename(copy, new)
    return [copy.name]


@command(
    "brick",
    "delete",
    Arg("NAME", BRICK, many=True),
    help=N_("Delete bricks that don't run"),
)
def delete(context, name):
    for brick in name:
        _stopped(brick)
    for brick in name:
        context.factory.del_brick(brick)
