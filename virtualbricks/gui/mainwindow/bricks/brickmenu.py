# -*- test-case-name: virtualbricks.tests.gui.mainwindow.bricks.test_brickmenu -*-
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
The menu of a brick, in the Bricks tab and in the Topology tab.

``menu()`` makes the ``Gio.Menu`` of a brick, and ``BrickActions`` the
group of actions its items call, under the prefix ``brick``. The menu has
Start or Stop, Configure, Rename, Duplicate, Connect To the bricks the
brick can plug into or take, When It Starts and When It Stops, and Delete;
a virtual machine has Resume. While the brick runs, Process slides to the
actions on its process: the control monitor, pause and continue, restart
and kill, and for a virtual machine suspend, reset and terminate.

When It Starts and When It Stops choose the event that the brick starts,
one or none: No Event, then every event of the project. An event that
isn't there any more stays, marked missing, until another is chosen.
"""

from __future__ import annotations

import functools
import signal

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402
from twisted.internet import defer, error, reactor  # noqa: E402
from twisted.logger import Logger  # noqa: E402

from virtualbricks import tools  # noqa: E402
from virtualbricks.bricks.virtualmachine import VirtualMachine  # noqa: E402
from virtualbricks.gui.mainwindow import tab  # noqa: E402
from virtualbricks.gui.mainwindow.bricks import brickinfo  # noqa: E402
from virtualbricks.gui.mainwindow.bricks.brickinfo import State  # noqa: E402
from virtualbricks.gui.mainwindow.tab import (  # noqa: E402
    menu_item,
    menu_of,
    menu_section,
)
from virtualbricks.gui.windows.renamedialog import RenameDialog  # noqa: E402
from virtualbricks.i18n import _  # noqa: E402
from virtualbricks.spawn import qemu_img  # noqa: E402
from virtualbricks.tools import is_running  # noqa: E402

logger = Logger()
not_supported = "Suspend/Resume not supported on this disk."
snapshot_error = "Error on snapshot"
resuming = "Resuming virtual machine {name}"
suspending = "Save snapshot on virtual machine {name}"
sending_signal = "Sending to process signal {signame}!"
sending_acpi = "send ACPI {acpievent}"
restarting = "Restarting process!"

GROUP = "brick"
# The snapshot that Suspend saves in the first disk, and Resume loads.
SNAPSHOT = "virtualbricks"
# Restart kills the process if it hasn't stopped after these seconds.
KILL_AFTER = 2
# The kinds of bricks without a settings panel, and without a console.
NO_PANEL = frozenset(("Router",))
NO_CONSOLE = frozenset(("Tap", "Capture"))
# The choices of an event: the action, the setting of the brick it
# changes, and the label of its submenu.
WHEN = (
    ("when-starts", "pon_vbevent", _("When It Starts")),
    ("when-stops", "poff_vbevent", _("When It Stops")),
)


_item = functools.partial(menu_item, GROUP)


def menu(brick, bricks, events, keys=False) -> Gio.Menu:
    """
    The menu of brick, among bricks and events. keys shows the keys of the
    Bricks tab next to the items: Enter, F2 and Delete.
    """

    def key(name):
        return name if keys else None

    running = is_running(brick)
    vm = isinstance(brick, VirtualMachine)
    targets = brickinfo.connectable(brick, bricks)
    connect_to = None
    if targets:
        submenu = menu_section(
            *(_item(t.name, "connect", t.name) for t in targets)
        )
        connect_to = Gio.MenuItem.new_submenu(_("Connect To"), submenu)
    names = [event.get_name() for event in events]
    when = [
        Gio.MenuItem.new_submenu(
            label, _events_menu(action, getattr(brick.config, setting), names)
        )
        for action, setting, label in WHEN
    ]
    process = None
    if running:
        process = Gio.MenuItem.new_submenu(
            _("Process {pid}").format(pid=brickinfo.process(brick)),
            _process_menu(brick),
        )
    return menu_of(
        menu_section(
            _item(_("Stop") if running else _("Start"), "startstop"),
            _item(_("Configure…"), "configure", keys=key("Return")),
        ),
        menu_section(
            _item(_("Rename…"), "rename", keys=key("F2")),
            _item(_("Duplicate"), "duplicate"),
            connect_to,
            *when,
        ),
        menu_section(_item(_("Resume"), "resume") if vm else None, process),
        menu_section(_item(_("Delete…"), "delete", keys=key("Delete"))),
    )


def _events_menu(action, current, names) -> Gio.Menu:
    """No Event, then the events: a choice of one, current, for action."""

    choices = [_item(name, action, name) for name in names]
    if current and current not in names:
        label = _("{name} (missing)").format(name=current)
        choices.append(_item(label, action, current))
    return menu_of(
        menu_section(_item(_("No Event"), action, "")),
        menu_section(*choices),
    )


def _process_menu(brick) -> Gio.Menu:
    vm = isinstance(brick, VirtualMachine)
    result = Gio.Menu()
    if brick.get_type() not in NO_CONSOLE:
        result.append_section(
            None, menu_section(_item(_("Open Control Monitor"), "console"))
        )
    result.append_section(
        None,
        menu_section(
            _item(_("Pause"), "pause"), _item(_("Continue"), "continue")
        ),
    )
    result.append_section(
        None,
        menu_section(
            _item(_("Suspend"), "suspend") if vm else None,
            _item(_("Reset"), "reset") if vm else None,
            _item(_("Restart"), "restart"),
        ),
    )
    result.append_section(
        None,
        menu_section(
            _item(_("Terminate"), "terminate") if vm else None,
            _item(_("Kill"), "kill"),
        ),
    )
    return result


class BrickActions(Gio.SimpleActionGroup):
    """What the items of the menu of a brick do."""

    def __init__(self, gui, brick, clock=None) -> None:
        super().__init__()
        self.gui = gui
        self.brick = brick
        self.clock = reactor if clock is None else clock
        for name, callback in (
            ("startstop", self.startstop),
            ("configure", self.configure),
            ("rename", self.rename),
            ("duplicate", self.duplicate),
            ("resume", self.resume),
            ("delete", self.delete),
            ("console", self.console),
            ("pause", self.pause),
            ("continue", self.cont),
            ("suspend", self.suspend),
            ("reset", self.reset),
            ("restart", self.restart),
            ("terminate", self.terminate),
            ("kill", self.kill),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda a, p, call=callback: call())
            self.add_action(action)
        action = Gio.SimpleAction.new("connect", GLib.VariantType.new("s"))
        action.connect("activate", self.on_connect)
        self.add_action(action)
        for name, setting, _label in WHEN:
            # the event chosen, which update() sets
            action = Gio.SimpleAction.new_stateful(
                name, GLib.VariantType.new("s"), GLib.Variant.new_string("")
            )
            action.connect("change-state", self.on_event_chosen, setting)
            self.add_action(action)
        self.update()

    def update(self) -> None:
        """The actions that the brick allows now."""

        state = brickinfo.state(self.brick)
        running = state is State.RUNNING
        vm = isinstance(self.brick, VirtualMachine)
        enabled = {
            "startstop": state in (State.RUNNING, State.STOPPED),
            "configure": self.brick.get_type() not in NO_PANEL,
            "rename": not running,
            "resume": vm,
            "console": running and self.brick.get_type() not in NO_CONSOLE,
            "pause": running,
            "continue": running,
            "suspend": running and vm,
            "reset": running and vm,
            "restart": running,
            "terminate": running and vm,
            "kill": running,
        }
        for name, value in enabled.items():
            self.lookup_action(name).set_enabled(value)
        # the events chosen, as the brick has them now
        for name, setting, _label in WHEN:
            self.lookup_action(name).set_state(
                GLib.Variant.new_string(getattr(self.brick.config, setting))
            )

    # The items

    def startstop(self) -> None:
        self.gui.startstop_brick(self.brick)

    def configure(self) -> None:
        self.gui.curtain_up(self.brick)

    def rename(self) -> None:
        RenameDialog(self.gui.brickfactory, self.brick).show(self.gui.window)

    def duplicate(self) -> None:
        self.gui.brickfactory.dup_brick(self.brick)

    def on_connect(self, action, target) -> None:
        other = self.gui.brickfactory.get_brick_by_name(target.get_string())
        if other is not None:
            brickinfo.connect(self.brick, other)

    def on_event_chosen(self, action, value, setting) -> None:
        self.brick.set({setting: value.get_string()})
        action.set_state(value)

    def resume(self) -> None:
        logger.debug(resuming, name=self.brick.get_name())
        self.gui.user_wait_action(resume(self.brick))

    def delete(self) -> None:
        self.gui.ask_remove_brick(self.brick)

    # The items of the process

    def console(self) -> None:
        self.brick.open_console()

    def _signal(self, number) -> None:
        logger.debug(sending_signal, signame=signal.Signals(number).name)
        try:
            self.brick.send_signal(number)
        except error.ProcessExitedAlready:
            pass

    def pause(self) -> None:
        self._signal(signal.SIGSTOP)

    def cont(self) -> None:
        self._signal(signal.SIGCONT)

    def suspend(self) -> None:
        logger.debug(suspending, name=self.brick.get_name())
        self.gui.user_wait_action(suspend(self.brick))

    def reset(self) -> None:
        logger.info(sending_acpi, acpievent="reset")
        self.brick.send(b"system_reset\n")

    def restart(self) -> None:
        restart(self.brick, self.clock)

    def terminate(self) -> None:
        logger.debug(sending_signal, signame="SIGTERM")
        self.brick.poweroff(term=True)

    def kill(self) -> None:
        logger.debug(sending_signal, signame="SIGKILL")
        self.brick.poweroff(kill=True)


def popup(widget, event, gui, brick, keys=False) -> Gtk.Menu:
    """
    Open the menu of brick: at the pointer, for a click on widget, or under
    widget when event is None, as for the Menu key. Keep the menu that it
    returns while it shows.
    """

    factory = gui.brickfactory
    return tab.popup(
        widget,
        event,
        menu(brick, factory.bricks, list(factory.iter_events()), keys),
        GROUP,
        BrickActions(gui, brick),
    )


# What the process items do to a brick


def restart(brick, clock) -> defer.Deferred:
    """Stop brick, killing it if it takes too long, and start it again."""

    logger.debug(restarting)
    stopped = brick.poweroff()
    call = clock.callLater(KILL_AFTER, brick.poweroff, kill=True)

    def cancel(passthru):
        if call.active():
            call.cancel()
        return passthru

    stopped.addBoth(cancel)
    stopped.addCallback(lambda _: brick.poweron())
    return stopped


def _first_disk(vm) -> str | None:
    disk = vm.disk("hda")
    if disk.is_cow():
        return disk.get_cow_path()
    if disk.image:
        return disk.image.path
    return None


def _not_supported() -> defer.Deferred:
    logger.error(not_supported)
    return defer.fail(
        RuntimeError(_("Suspend/Resume not supported on this disk."))
    )


def suspend(vm) -> defer.Deferred:
    """Save the state of a virtual machine in its first disk, and stop it."""

    path = _first_disk(vm)
    if path is None:
        return _not_supported()
    image_type = tools.image_type_from_file(path)
    if image_type not in (tools.ImageFormat.QCOW2, tools.ImageFormat.QCOW3):
        return _not_supported()
    vm.send(f"savevm {SNAPSHOT}\n".encode())
    return vm.poweroff()


def resume(vm) -> defer.Deferred:
    """Start a virtual machine from what Suspend saved in its first disk."""

    def found(output):
        if output.find(SNAPSHOT) == -1:
            raise RuntimeError(_("Cannot find suspend point."))

    def load(_):
        if vm.proc is not None:
            vm.send(f"loadvm {SNAPSHOT}\n".encode())
        else:
            return vm.poweron(SNAPSHOT)

    def failed(failure):
        logger.failure(snapshot_error, failure)
        return failure

    path = _first_disk(vm)
    if path is None:
        return _not_supported()
    output = qemu_img(["snapshot", "-l", path])
    output.addCallback(found)
    output.addCallback(load)
    output.addErrback(failed)
    return output
