# -*- test-case-name: virtualbricks.tests.remote.test_commands -*-
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
The AMP commands of the windows of another Virtualbricks, in protocol 2
beside the typed commands of the console (page 19 §7). A connection speaks
them once Hello has agreed on 2, and they pass the same checks.

``Follow`` asks the Virtualbricks that runs the bricks for its project and
its changes. It sends them as pushes, commands that it calls on the program
and that need no answer: ``Opened`` when a project opens, then ``Changed``
for each image, brick and event, then ``Synced``; after that, a push for
each change, and ``Logged`` for each message of its log. A table, a state,
the settings and a message are JSON in a text, since AMP has no tables.

Like ampcommands, it loads nothing but Twisted's amp and the errors of
ampwire and ampcommands, so that a program can import it, or copy it.
"""

from twisted.protocols import amp

from virtualbricks.console.ampcommands import ERRORS

# The protocol of these commands, which Hello agrees on.
PROTOCOL = 2

# the kinds of the objects of a project, as the pushes name them
BRICK = "brick"
EVENT = "event"
IMAGE = "image"


class Follow(amp.Command):
    """
    Send the project, then each change, and the messages of the log: the
    project open and the version, once the project is sent.
    """

    response = [
        (b"project", amp.Unicode(optional=True)),
        (b"version", amp.Unicode()),
    ]
    errors = ERRORS


class Apply(amp.Command):
    """
    The OK of the panel of a brick, an event or an image: what it changed,
    ``changes``, ``links`` and ``extras``, JSON as remote.drafts writes it.
    All or nothing.
    """

    arguments = [
        (b"kind", amp.Unicode()),
        (b"name", amp.Unicode()),
        (b"changes", amp.Unicode()),
        (b"links", amp.Unicode()),
        (b"extras", amp.Unicode()),
    ]
    response = []
    errors = ERRORS


class Connect(amp.Command):
    """
    Connect a brick to another, as a drop does: a free plug, or a new card
    of a machine. Whether it could.
    """

    arguments = [(b"source", amp.Unicode()), (b"target", amp.Unicode())]
    response = [(b"connected", amp.Boolean())]
    errors = ERRORS


# The questions of programs.QEMU_QUESTIONS, whose answers QemuFacts gives.
QEMU_ANSWERS = (
    "version",
    "options",
    "machines",
    "cpus",
    "devices",
    "displays",
    "audio_drivers",
    "netdevs",
    "accelerators",
)


class QemuFacts(amp.Command):
    """
    What the QEMU program of that name has, as the texts it printed: its
    path, and its answer to each question, JSON ``[out, err, status]``, a
    value each, since all of them are more than AMP carries in one.
    NotFound if there is none.
    """

    arguments = [(b"program", amp.Unicode())]
    response = [(b"path", amp.Unicode())] + [
        (name.encode(), amp.Unicode()) for name in QEMU_ANSWERS
    ]
    errors = ERRORS


class MachineProperties(amp.Command):
    """
    The text of the properties of a machine type of a QEMU program, as
    ``-machine TYPE,help`` prints it; the default type if machine is empty.
    """

    arguments = [(b"program", amp.Unicode()), (b"machine", amp.Unicode())]
    response = [(b"text", amp.Unicode())]
    errors = ERRORS


class UsbDevices(amp.Command):
    """The USB devices of the machine: JSON ``[{id, description}]``."""

    response = [(b"devices", amp.Unicode())]
    errors = ERRORS


class ImageFacts(amp.Command):
    """
    What the file path is: ``file``, JSON ``{size, mtime, taken}``, the
    time in nanoseconds; ``info``, what ``qemu-img info --output=json``
    printed; ``others``, JSON ``[[project, image]]``, the images of the other
    projects of the workspace with that file. NotFound if it isn't there.
    """

    arguments = [(b"path", amp.Unicode())]
    response = [
        (b"file", amp.Unicode()),
        (b"info", amp.Unicode()),
        (b"others", amp.Unicode()),
    ]
    errors = ERRORS


class MakeImage(amp.Command):
    """
    Make the file of an empty disk: path, its format, qcow2 or raw, and its
    size in bytes. BadArgument if the file is there already.
    """

    arguments = [
        (b"path", amp.Unicode()),
        (b"format", amp.Unicode()),
        (b"size", amp.Integer()),
    ]
    response = []
    errors = ERRORS


class StartOver(amp.Command):
    """
    The private copy of a disk of a machine goes, with its changes, to the
    trash if there is one: whether it went there.
    """

    arguments = [(b"vm", amp.Unicode()), (b"device", amp.Unicode())]
    response = [(b"trashed", amp.Boolean())]
    errors = ERRORS


class TrashFile(amp.Command):
    """
    A file of the workspace that no image uses goes to the trash, or is
    deleted without one: whether it went to the trash.
    """

    arguments = [(b"path", amp.Unicode())]
    response = [(b"trashed", amp.Boolean())]
    errors = ERRORS


class Relink(amp.Command):
    """
    Give the image name the file path, and the private copies made on the
    image with it.
    """

    arguments = [(b"name", amp.Unicode()), (b"path", amp.Unicode())]
    response = []
    errors = ERRORS


class ProjectNames(amp.Command):
    """The names of the projects of the workspace, sorted."""

    response = [(b"names", amp.ListOf(amp.Unicode()))]
    errors = ERRORS


class ProjectSummary(amp.Command):
    """
    What the list of the projects shows of one, as JSON: its name, path,
    description, modified, bricks ``{type: count}``, events, images
    ``[{name, path, found}]`` and problem, null if the project file reads.
    NotFound if there is none.
    """

    arguments = [(b"name", amp.Unicode())]
    response = [(b"summary", amp.Unicode())]
    errors = ERRORS


class DiskUsage(amp.Command):
    """The space that a project takes, in bytes: its private disks, the rest."""

    arguments = [(b"name", amp.Unicode())]
    response = [
        (b"private_disks", amp.Integer()),
        (b"other_files", amp.Integer()),
    ]
    errors = ERRORS


class Readme(amp.Command):
    """The README of the open project."""

    response = [(b"text", amp.Unicode())]
    errors = ERRORS


class SetReadme(amp.Command):
    """Write the README of the open project, when the project is saved."""

    arguments = [(b"text", amp.Unicode())]
    response = []
    errors = ERRORS


class ReadmePicture(amp.Command):
    """
    A picture of the README of project name, a file of its folder: its bytes
    from offset, as many as a value carries, and the size of the file.
    """

    arguments = [
        (b"name", amp.Unicode()),
        (b"path", amp.Unicode()),
        (b"offset", amp.Integer()),
    ]
    response = [(b"data", amp.String()), (b"size", amp.Integer())]
    errors = ERRORS


class SetKsm(amp.Command):
    """Turn KSM on or off: whether it runs afterwards."""

    arguments = [(b"enable", amp.Boolean())]
    response = [(b"enabled", amp.Boolean())]
    errors = ERRORS


class Folder(amp.Command):
    """
    What completes path, a file or a folder there: the entries of its
    folder that start with its last part, folders with a / after them, at
    most 200, and whether there are more.
    """

    arguments = [(b"path", amp.Unicode())]
    response = [
        (b"entries", amp.ListOf(amp.Unicode())),
        (b"more", amp.Boolean()),
    ]
    errors = ERRORS


class Attach(amp.ProtocolSwitchCommand):
    """
    Carry the bytes of a console of a running brick both ways, from the
    answer on: console is monitor, its control monitor, or serial, the
    serial socket of a machine. The connection carries nothing else then.
    """

    arguments = [(b"brick", amp.Unicode()), (b"console", amp.Unicode())]
    response = []
    errors = ERRORS


class _Push(amp.Command):
    """A command that Virtualbricks calls on a program that follows it."""

    requiresAnswer = False


class Opened(_Push):
    """
    A project opened, and the copy starts again: its name, the settings, of
    Virtualbricks and of the project, and what the machine has.
    """

    arguments = [
        (b"project", amp.Unicode(optional=True)),
        (b"settings", amp.Unicode()),
        (b"machine", amp.Unicode()),
    ]


class Changed(_Push):
    """
    A brick, an event or an image, new or changed: its table, as the
    project file writes it, and its state.
    """

    arguments = [
        (b"kind", amp.Unicode()),
        (b"name", amp.Unicode()),
        (b"table", amp.Unicode()),
        (b"state", amp.Unicode()),
    ]


class Renamed(_Push):
    """A brick, an event or an image has a new name."""

    arguments = [
        (b"kind", amp.Unicode()),
        (b"old", amp.Unicode()),
        (b"new", amp.Unicode()),
    ]


class Removed(_Push):
    """A brick or an event is deleted, an image removed."""

    arguments = [(b"kind", amp.Unicode()), (b"name", amp.Unicode())]


class Synced(_Push):
    """The whole project has been sent."""


class SettingsChanged(_Push):
    """The settings, of Virtualbricks or of the project, changed."""

    arguments = [(b"settings", amp.Unicode())]


class Logged(_Push):
    """A message of the log, info and above."""

    arguments = [(b"message", amp.Unicode())]


class Quitting(_Push):
    """Virtualbricks quits."""


# What a program calls, and what Virtualbricks calls on it.
FROM_PROGRAM = (
    Follow,
    Apply,
    Connect,
    QemuFacts,
    MachineProperties,
    UsbDevices,
    ImageFacts,
    MakeImage,
    StartOver,
    TrashFile,
    Relink,
    ProjectNames,
    ProjectSummary,
    DiskUsage,
    Readme,
    SetReadme,
    ReadmePicture,
    SetKsm,
    Folder,
    Attach,
)
PUSHES = (
    Opened,
    Changed,
    Renamed,
    Removed,
    Synced,
    SettingsChanged,
    Logged,
    Quitting,
)
