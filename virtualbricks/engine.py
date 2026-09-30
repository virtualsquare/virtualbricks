# -*- test-case-name: virtualbricks.tests.test_engine -*-
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
What the windows change, run or ask of the machine, through one object: the
engine (page 19 §6).

The windows read the bricks, the events and the images of ``engine.factory``
and follow its signals; whatever they do to them, to the projects, to the
settings, and what they ask of the machine goes through the engine. Each
call returns a Deferred, so that the windows wait for an engine on this
machine as they would for one on another, and a refusal is its failure.

``engine.machine`` has what the windows read of the machine of the bricks
at once, without asking: its settings, its QEMU programs, the files of the
images and of the private copies; and the facts of the files that qemu-img
reads, once each while a file doesn't change.

``LocalEngine`` does what the windows did before, on the factory of this
process. It loads no GTK.
"""

import os
import signal

from twisted.internet import defer, error, reactor, threads

from virtualbricks import ksm
from virtualbricks.bricks import brickinfo, restart
from virtualbricks.bricks.draft import apply
from virtualbricks.bricks.event import is_event
from virtualbricks.bricks.virtualmachine import (
    get_usb_devices,
    is_disk_image,
    resume,
    suspend,
)
from virtualbricks.config import images
from virtualbricks.config.settings import (
    PROJECT_KEYS,
    get_setting,
    set_setting,
    store_settings,
)
from virtualbricks.config.workspace import projects
from virtualbricks.programs import programs as known_programs, qemu_programs
from virtualbricks.qemu import run


class LocalMachine:
    """What the windows read of this machine, which runs the bricks."""

    def __init__(self, workspace, qemu_img=None) -> None:
        self.workspace = workspace
        # what qemu-img info says of each file, while it doesn't change
        self.infos = images.InfoCache(qemu_img)

    def exists(self, path) -> bool:
        return os.path.exists(path)

    def taken(self, path) -> int | None:
        """The space the file path takes; None if it isn't there."""

        return images.space_taken(path)

    def changed(self, path) -> float | None:
        """When the file path changed, in seconds; None if it isn't there."""

        try:
            return os.stat(path).st_mtime
        except OSError:
            return None

    def other_projects(self, path) -> list[tuple[str, str]]:
        """The images of the other projects whose file is path."""

        return images.other_projects(self.workspace, path)

    def setting(self, name):
        """A setting of Virtualbricks, or of the open project."""

        return get_setting(name)

    def qemu_programs(self) -> list[str]:
        """The names of the QEMU system emulators, for a machine to use."""

        return qemu_programs(get_setting("qemu_path"))


class LocalEngine:
    """
    The engine of the windows of the Virtualbricks that runs the bricks: the
    calls of the factory, of the workspace and of the programs of this
    machine.
    """

    # the windows are those of the Virtualbricks of this process
    local = True

    def __init__(
        self,
        factory,
        workspace=None,
        clock=None,
        qemu_img=None,
        usb_devices=None,
        programs=None,
        which=None,
    ) -> None:
        # what the windows read, and what the engine changes
        self.factory = factory
        self.workspace = projects if workspace is None else workspace
        self.clock = reactor if clock is None else clock
        self.qemu_img = run.qemu_img if qemu_img is None else qemu_img
        self.machine = LocalMachine(self.workspace, self.qemu_img)
        self.usb_devices = (
            get_usb_devices if usb_devices is None else usb_devices
        )
        # what QEMU answers, asked once per program, and where it is
        self.programs = known_programs if programs is None else programs
        self.which = run.which if which is None else which

    # The bricks

    def start(self, brick) -> defer.Deferred:
        return defer.maybeDeferred(brick.poweron)

    def stop(self, brick) -> defer.Deferred:
        return defer.maybeDeferred(brick.poweroff)

    def terminate(self, brick) -> defer.Deferred:
        """Stop brick with SIGTERM."""

        return defer.maybeDeferred(brick.poweroff, term=True)

    def kill(self, brick) -> defer.Deferred:
        return defer.maybeDeferred(brick.poweroff, kill=True)

    def restart(self, brick) -> defer.Deferred:
        """Stop brick, killing it if it takes too long, and start it."""

        return defer.maybeDeferred(restart, brick, self.clock)

    def pause(self, brick) -> defer.Deferred:
        return defer.maybeDeferred(self._signal, brick, signal.SIGSTOP)

    def continue_(self, brick) -> defer.Deferred:
        """Let a paused brick go on."""

        return defer.maybeDeferred(self._signal, brick, signal.SIGCONT)

    def _signal(self, brick, number) -> None:
        try:
            brick.send_signal(number)
        except error.ProcessExitedAlready:
            pass

    def suspend(self, vm) -> defer.Deferred:
        """Save the state of a machine in its first disk, and stop it."""

        return defer.maybeDeferred(suspend, vm)

    def resume(self, vm) -> defer.Deferred:
        """Start a machine from the state that suspend saved."""

        return defer.maybeDeferred(resume, vm)

    def reset(self, vm) -> defer.Deferred:
        """Reset a running machine, as its reset button."""

        return defer.maybeDeferred(vm.send, b"system_reset\n")

    def open_console(self, brick) -> defer.Deferred:
        """Open the control monitor of a running brick in a terminal."""

        return defer.maybeDeferred(brick.open_console)

    def new_brick(self, type, name) -> defer.Deferred:
        """A new brick of type: its Deferred fires with the brick."""

        return defer.maybeDeferred(self.factory.new_brick, type, name)

    def connect(self, source, destination) -> defer.Deferred:
        """Connect source to destination, as a drop does; False if it can't."""

        return defer.maybeDeferred(brickinfo.connect, source, destination)

    # The bricks, the events and the images

    def rename(self, item, name) -> defer.Deferred:
        """Rename a brick, an event or an image, and what names it."""

        return defer.maybeDeferred(self.factory.rename_item, item, name)

    def duplicate(self, item) -> defer.Deferred:
        """A copy of a brick or an event: its Deferred fires with it."""

        if is_event(item):
            return defer.maybeDeferred(self.factory.duplicate_event, item)
        return defer.maybeDeferred(self.factory.duplicate_brick, item)

    def remove(self, item) -> defer.Deferred:
        """Delete a brick or an event; remove an image from the library."""

        if is_disk_image(item):
            return defer.maybeDeferred(self.factory.remove_image, item)
        if is_event(item):
            return defer.maybeDeferred(self.factory.remove_event, item)
        return defer.maybeDeferred(self.factory.remove_brick, item)

    def update_config(self, item, changes) -> defer.Deferred:
        """Set the settings of changes, a dict, all or none."""

        return defer.maybeDeferred(item.update_config, changes)

    def apply(self, draft) -> defer.Deferred:
        """The OK of a panel: give its brick, event or image the draft."""

        return defer.maybeDeferred(apply, draft)

    # The events

    def new_event(self, name, delay) -> defer.Deferred:
        """A new event that waits delay seconds: its Deferred fires with it."""

        def new():
            event = self.factory.new_event(name)
            event.update_config({"delay": delay})
            return event

        return defer.maybeDeferred(new)

    def start_event(self, event) -> defer.Deferred:
        """Let an event wait, then run its actions."""

        return defer.maybeDeferred(event.poweron)

    def stop_event(self, event) -> defer.Deferred:
        return defer.maybeDeferred(event.poweroff)

    def run_event(self, event) -> defer.Deferred:
        """Run the actions of an event now."""

        return defer.maybeDeferred(event.run_actions)

    # The images and their files

    def new_image(self, name, path, description="") -> defer.Deferred:
        """Add an image of the file path: its Deferred fires with it."""

        return defer.maybeDeferred(
            self.factory.new_image, name, path, description
        )

    def make_image(self, path, fmt, size) -> defer.Deferred:
        """Make the file of an empty disk of size bytes, in format fmt."""

        return self.qemu_img(["create", "-q", "-f", fmt, path, str(size)])

    def image_info(self, path) -> defer.Deferred:
        """What qemu-img says of the file path, an ImageInfo."""

        return images.read_info(path, self.qemu_img)

    def relink(self, image, path) -> defer.Deferred:
        """Give image the file path, and its private copies with it."""

        return images.relink(self.factory, image, path, self.qemu_img)

    def discard_file(self, path) -> defer.Deferred:
        """
        Move the file path to the trash, or delete it without one; the
        Deferred fires with True if it went to the trash.
        """

        return defer.maybeDeferred(
            images.discard, path, self.workspace.trasher
        )

    def start_over(self, vm, device) -> defer.Deferred:
        """The private copy of a disk goes: the next start makes one."""

        return defer.maybeDeferred(
            images.start_over, vm, device, self.workspace.trasher
        )

    # The projects

    def project_summaries(self) -> defer.Deferred:
        """The summaries of the projects of the workspace."""

        return defer.maybeDeferred(self.workspace.summaries)

    def disk_usage(self, name) -> defer.Deferred:
        """The space the project name takes, counted in a thread."""

        return threads.deferToThread(self.workspace.disk_usage, name)

    def save_project(self) -> defer.Deferred:
        return defer.maybeDeferred(self.workspace.save, self.factory)

    def open_project(self, name) -> defer.Deferred:
        """Open the project name: its Deferred fires with the report."""

        return defer.maybeDeferred(self.workspace.open, name, self.factory)

    def new_project(self, name, description="") -> defer.Deferred:
        """Make the project name, and open it."""

        def new():
            self.workspace.create(name, description)
            return self.workspace.open(name, self.factory)

        return defer.maybeDeferred(new)

    def restore_last(self) -> defer.Deferred:
        """Open the project open last, or else a new one."""

        return defer.maybeDeferred(self.workspace.restore_last, self.factory)

    def rename_project(self, name, new) -> defer.Deferred:
        def rename():
            # the sockets of the bricks of the open project, with its name
            bricks = None
            current = self.workspace.current
            if current is not None and current.name == name:
                bricks = [brick.name for brick in self.factory.bricks]
            self.workspace.rename(name, new, bricks=bricks)

        return defer.maybeDeferred(rename)

    def duplicate_project(self, name, new) -> defer.Deferred:
        return defer.maybeDeferred(self.workspace.duplicate, name, new)

    def remove_project(self, name, trash) -> defer.Deferred:
        """Move the project name to the trash, or delete it for good."""

        if trash:
            return defer.maybeDeferred(self.workspace.trash, name)
        return defer.maybeDeferred(self.workspace.delete, name)

    def readme(self) -> defer.Deferred:
        """The README of the open project."""

        return defer.maybeDeferred(self.workspace.current.get_description)

    def set_readme(self, text) -> defer.Deferred:
        return defer.maybeDeferred(
            self.workspace.current.set_description, text
        )

    # The settings

    def set_settings(self, values) -> defer.Deferred:
        """
        Set the settings of values, a dict, of Virtualbricks and of the open
        project, and write them where they are kept.
        """

        def set_all():
            for name, value in values.items():
                set_setting(name, value)
            if any(name in PROJECT_KEYS for name in values):
                if self.workspace.current is not None:
                    self.workspace.save(self.factory)
            if any(name not in PROJECT_KEYS for name in values):
                store_settings()

        return defer.maybeDeferred(set_all)

    def set_ksm(self, enable) -> defer.Deferred:
        """Turn KSM on or off: the Deferred fires with its state then."""

        return ksm.set_ksm(enable)

    # What the machine has

    def lacks(self, kind) -> defer.Deferred:
        """What a kind of New Brick lacks, an Issue, or None."""

        return defer.maybeDeferred(
            brickinfo.issue,
            kind,
            get_setting("vde_path"),
            get_setting("qemu_path"),
        )

    def qemu(self, program) -> defer.Deferred:
        """
        What the QEMU program has, a QemuInfo: the program of that name in
        the folder of the setting, or else in PATH; FileNotFoundError if
        there is none.
        """

        finding = defer.maybeDeferred(self.which, program)
        finding.addCallback(self.programs.qemu)
        return finding

    def machine_properties(self, info, machine) -> defer.Deferred:
        """The properties of a machine type of QEMU; the default if empty."""

        return self.programs.machine_properties(info, machine)

    def usb(self) -> defer.Deferred:
        """The USB devices of the machine."""

        return defer.maybeDeferred(self.usb_devices)

    def quit(self) -> defer.Deferred:
        """Quit Virtualbricks, refused while bricks run."""

        return defer.maybeDeferred(self.factory.quit)
