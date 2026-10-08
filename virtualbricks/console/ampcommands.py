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

# Written by virtualbricks/console/ampgen.py from the table of the console:
# don't change it by hand, run python -m virtualbricks.console.ampgen.

"""
The typed commands of the AMP socket, protocol 2: one for each command
of the console, with its arguments. A connection speaks them once Hello has
agreed on 2::

    vb = await endpoints.connectProtocol(endpoint, amp.AMP())
    await vb.callRemote(Hello, protocols=[PROTOCOL])
    answer = await vb.callRemote(BrickStart, name=["sw1", "vm1"])

Each answers the lines of the console. NotFound and BadArgument say that
nothing was done, CommandFailed that the command failed on the way.
Like ampwire, it loads nothing but Twisted's amp and ampwire, so that a
program can import it, or copy it.
"""

from twisted.protocols import amp

from virtualbricks.console.ampwire import (
    AnswerTooLong,
    CommandFailed,
    TokenNeeded,
)

# The protocol of these commands, which Hello agrees on.
PROTOCOL = 2


class NotFound(CommandFailed):
    """A name of the command names nothing of the project."""


class BadArgument(CommandFailed):
    """An argument of the command isn't one it takes."""


class ProtocolNeeded(Exception):
    """The connection hasn't agreed on this protocol with Hello."""


ERRORS = {
    NotFound: b"NOT_FOUND",
    BadArgument: b"BAD_ARGUMENT",
    ProtocolNeeded: b"PROTOCOL_NEEDED",
    CommandFailed: b"COMMAND_FAILED",
    AnswerTooLong: b"ANSWER_TOO_LONG",
    TokenNeeded: b"TOKEN_NEEDED",
}
LINES: list[tuple[bytes, amp.Argument]] = [
    (b"lines", amp.ListOf(amp.Unicode()))
]
PAIR: list[tuple[bytes, amp.Argument]] = [
    (b"key", amp.Unicode()),
    (b"value", amp.Unicode()),
]
CWD = (b"cwd", amp.Unicode(optional=True))


class BrickTypes(amp.Command):
    """
    brick types: The kinds of brick, and what this computer lacks for each.
    """

    arguments = [CWD]
    response = LINES
    errors = ERRORS


class BrickList(amp.Command):
    """brick list: The bricks, their state and settings."""

    arguments = [CWD]
    response = LINES
    errors = ERRORS


class BrickNew(amp.Command):
    """
    brick new KIND [NAME]: Make a brick; without a name, the kind's and the
    first free number.
    """

    arguments = [
        (b"kind", amp.Unicode()),
        (b"name", amp.Unicode(optional=True)),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class BrickShow(amp.Command):
    """brick show NAME: A brick's state, links and keys."""

    arguments = [
        (b"name", amp.Unicode()),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class BrickKeys(amp.Command):
    """
    brick keys KIND|NAME [KEY]: The keys of a kind of brick or of a brick,
    or one, with what each is for.
    """

    arguments = [
        (b"kind_name", amp.Unicode()),
        (b"key", amp.Unicode(optional=True)),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class BrickSet(amp.Command):
    """brick set NAME KEY=VALUE…: Change keys of a brick, all or none."""

    arguments = [
        (b"name", amp.Unicode()),
        (b"key_value", amp.AmpList(PAIR)),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class BrickUnset(amp.Command):
    """brick unset NAME KEY…: Put keys of a brick back to their defaults."""

    arguments = [
        (b"name", amp.Unicode()),
        (b"key", amp.ListOf(amp.Unicode())),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class BrickStart(amp.Command):
    """
    brick start NAME…: Start bricks, after those they plug into, and wait
    for them.
    """

    arguments = [
        (b"name", amp.ListOf(amp.Unicode())),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class BrickStop(amp.Command):
    """brick stop NAME…: Stop bricks, and wait until their programs end."""

    arguments = [
        (b"name", amp.ListOf(amp.Unicode())),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class BrickKill(amp.Command):
    """brick kill NAME…: Kill the programs of bricks."""

    arguments = [
        (b"name", amp.ListOf(amp.Unicode())),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class BrickRestart(amp.Command):
    """
    brick restart NAME…: Stop bricks, killing them after two seconds, and
    start them.
    """

    arguments = [
        (b"name", amp.ListOf(amp.Unicode())),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class BrickPause(amp.Command):
    """brick pause NAME…: Pause the programs of bricks."""

    arguments = [
        (b"name", amp.ListOf(amp.Unicode())),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class BrickContinue(amp.Command):
    """brick continue NAME…: Let paused bricks go on."""

    arguments = [
        (b"name", amp.ListOf(amp.Unicode())),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class BrickSuspend(amp.Command):
    """
    brick suspend VM: Save a machine's state in its first disk, and stop it.
    """

    arguments = [
        (b"vm", amp.Unicode()),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class BrickResume(amp.Command):
    """brick resume VM: Start a machine from the state that suspend saved."""

    arguments = [
        (b"vm", amp.Unicode()),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class BrickReset(amp.Command):
    """brick reset VM: Reset a running machine, as its reset button."""

    arguments = [
        (b"vm", amp.Unicode()),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class BrickMonitor(amp.Command):
    """
    brick monitor NAME: Open the control monitor of a running brick in a
    terminal.
    """

    arguments = [
        (b"name", amp.Unicode()),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class BrickConnect(amp.Command):
    """
    brick connect NAME TARGET…: Plug a brick into switches: a wire or a
    Netemu's ends, left then right.
    """

    arguments = [
        (b"name", amp.Unicode()),
        (b"target", amp.ListOf(amp.Unicode())),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class BrickDisconnect(amp.Command):
    """
    brick disconnect NAME [END]: Unplug a brick, or one end of a wire or a
    Netemu.
    """

    arguments = [
        (b"name", amp.Unicode()),
        (b"end", amp.Unicode(optional=True)),  # left or right
        CWD,
    ]
    response = LINES
    errors = ERRORS


class BrickCardAdd(amp.Command):
    """
    brick card add VM KIND [OPTIONS…]: Add a network card: plug and its
    target, socket, or hostonly; model= and mac= are its own.
    """

    arguments = [
        (b"vm", amp.Unicode()),
        (b"kind", amp.Unicode()),  # plug, socket or hostonly
        (b"options", amp.ListOf(amp.Unicode(), optional=True)),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class BrickCardSet(amp.Command):
    """
    brick card set VM CARD KEY=VALUE…: Change a card's model, mac, or
    target: a switch, hostonly, or nothing.
    """

    arguments = [
        (b"vm", amp.Unicode()),
        (b"card", amp.Unicode()),
        (b"key_value", amp.AmpList(PAIR)),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class BrickCardRemove(amp.Command):
    """brick card remove VM CARD…: Take network cards out of a machine."""

    arguments = [
        (b"vm", amp.Unicode()),
        (b"card", amp.ListOf(amp.Unicode())),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class BrickRename(amp.Command):
    """brick rename NAME NEW: Rename a brick."""

    arguments = [
        (b"name", amp.Unicode()),
        (b"new", amp.Unicode()),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class BrickDuplicate(amp.Command):
    """
    brick duplicate NAME [NEW]: Copy a brick, with its links; without a new
    name, its name with the next free number.
    """

    arguments = [
        (b"name", amp.Unicode()),
        (b"new", amp.Unicode(optional=True)),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class BrickDelete(amp.Command):
    """
    brick delete NAME…: Delete bricks that don't run, and the actions that
    start or stop them.
    """

    arguments = [
        (b"name", amp.ListOf(amp.Unicode())),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class EventList(amp.Command):
    """event list: The events, their state and actions."""

    arguments = [CWD]
    response = LINES
    errors = ERRORS


class EventNew(amp.Command):
    """
    event new [NAME]: Make an event; without a name, new_event or the next
    free one.
    """

    arguments = [
        (b"name", amp.Unicode(optional=True)),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class EventShow(amp.Command):
    """
    event show NAME: An event's delay, its actions numbered, what starts it.
    """

    arguments = [
        (b"name", amp.Unicode()),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class EventSet(amp.Command):
    """event set NAME KEY=VALUE…: Change an event's delay or icon."""

    arguments = [
        (b"name", amp.Unicode()),
        (b"key_value", amp.AmpList(PAIR)),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class EventActionAdd(amp.Command):
    """
    event action add NAME WHAT [SUBJECT] [--at N]: Add an action: start or
    stop a brick or an event, or a command of the console or the shell.
    """

    arguments = [
        (b"name", amp.Unicode()),
        (b"what", amp.Unicode()),  # start, stop, console or shell
        (b"subject", amp.Unicode(optional=True)),
        (b"at", amp.Integer(optional=True)),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class EventActionRemove(amp.Command):
    """
    event action remove NAME N…: Remove actions of an event, by their
    numbers.
    """

    arguments = [
        (b"name", amp.Unicode()),
        (b"n", amp.ListOf(amp.Integer())),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class EventActionMove(amp.Command):
    """
    event action move NAME N TO: Move an action of an event to another
    place.
    """

    arguments = [
        (b"name", amp.Unicode()),
        (b"n", amp.Integer()),
        (b"to", amp.Integer()),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class EventStart(amp.Command):
    """
    event start NAME…: Start events: each waits its delay, then runs its
    actions.
    """

    arguments = [
        (b"name", amp.ListOf(amp.Unicode())),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class EventStop(amp.Command):
    """event stop NAME…: Stop events that wait."""

    arguments = [
        (b"name", amp.ListOf(amp.Unicode())),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class EventRun(amp.Command):
    """event run NAME…: Run the actions of events now, and wait for them."""

    arguments = [
        (b"name", amp.ListOf(amp.Unicode())),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class EventRename(amp.Command):
    """
    event rename NAME NEW: Rename an event, and every brick and action that
    names it.
    """

    arguments = [
        (b"name", amp.Unicode()),
        (b"new", amp.Unicode()),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class EventDuplicate(amp.Command):
    """
    event duplicate NAME [NEW]: Copy an event; without a new name, its name
    with the next free number.
    """

    arguments = [
        (b"name", amp.Unicode()),
        (b"new", amp.Unicode(optional=True)),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class EventDelete(amp.Command):
    """
    event delete NAME…: Delete events, the actions that start or stop them,
    and the on_start and on_stop that name them.
    """

    arguments = [
        (b"name", amp.ListOf(amp.Unicode())),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class ProjectList(amp.Command):
    """project list: The projects of the workspace."""

    arguments = [CWD]
    response = LINES
    errors = ERRORS


class ProjectShow(amp.Command):
    """project show: The open project."""

    arguments = [CWD]
    response = LINES
    errors = ERRORS


class ProjectOpen(amp.Command):
    """project open NAME: Save the open project and open another."""

    arguments = [
        (b"name", amp.Unicode()),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class ProjectNew(amp.Command):
    """project new NAME: Save the open project, make a new one and open it."""

    arguments = [
        (b"name", amp.Unicode()),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class ProjectSave(amp.Command):
    """project save: Save the open project now."""

    arguments = [CWD]
    response = LINES
    errors = ERRORS


class ProjectRename(amp.Command):
    """project rename NAME NEW: Rename a project."""

    arguments = [
        (b"name", amp.Unicode()),
        (b"new", amp.Unicode()),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class ProjectDuplicate(amp.Command):
    """project duplicate NAME NEW: Copy a project, its disks included."""

    arguments = [
        (b"name", amp.Unicode()),
        (b"new", amp.Unicode()),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class ProjectDelete(amp.Command):
    """
    project delete NAME [--force]: Move a project to the trash; without one,
    --force deletes it for good.
    """

    arguments = [
        (b"name", amp.Unicode()),
        (b"force", amp.Boolean(optional=True)),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class Help(amp.Command):
    """help [TOPIC…]: The commands, a noun's verbs, or one command."""

    arguments = [
        (b"topic", amp.ListOf(amp.Unicode(), optional=True)),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class Status(amp.Command):
    """
    status: What runs: the bricks with their processes, the events that
    wait.
    """

    arguments = [CWD]
    response = LINES
    errors = ERRORS


class Quit(amp.Command):
    """quit: Quit Virtualbricks; refused while bricks run."""

    arguments = [CWD]
    response = LINES
    errors = ERRORS


class Source(amp.Command):
    """
    source FILE: Run the commands of a file, one a line, up to the first
    error.
    """

    arguments = [
        (b"file", amp.Unicode()),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class ImageList(amp.Command):
    """image list: The disk images and their users."""

    arguments = [CWD]
    response = LINES
    errors = ERRORS


class ImageAdd(amp.Command):
    """
    image add NAME PATH [KEY=VALUE…]: Add an image file to the project;
    description= says what it is.
    """

    arguments = [
        (b"name", amp.Unicode()),
        (b"path", amp.Unicode()),
        (b"key_value", amp.AmpList(PAIR, optional=True)),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class ImageShow(amp.Command):
    """image show NAME: An image's file, description and users."""

    arguments = [
        (b"name", amp.Unicode()),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class ImageSet(amp.Command):
    """image set NAME KEY=VALUE…: Change the description of an image."""

    arguments = [
        (b"name", amp.Unicode()),
        (b"key_value", amp.AmpList(PAIR)),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class ImageRename(amp.Command):
    """image rename NAME NEW: Rename an image, in the disks that use it too."""

    arguments = [
        (b"name", amp.Unicode()),
        (b"new", amp.Unicode()),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class ImageDelete(amp.Command):
    """
    image delete NAME: Remove an image from the project; its file and the
    private copies stay.
    """

    arguments = [
        (b"name", amp.Unicode()),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class SettingShow(amp.Command):
    """
    setting show [KEY]: The settings of Virtualbricks and of the open
    project.
    """

    arguments = [
        (b"key", amp.Unicode(optional=True)),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class SettingSet(amp.Command):
    """setting set KEY=VALUE…: Change settings, all or none."""

    arguments = [
        (b"key_value", amp.AmpList(PAIR)),
        CWD,
    ]
    response = LINES
    errors = ERRORS


class SettingUnset(amp.Command):
    """setting unset KEY…: Put settings back to their defaults."""

    arguments = [
        (b"key", amp.ListOf(amp.Unicode())),
        CWD,
    ]
    response = LINES
    errors = ERRORS
