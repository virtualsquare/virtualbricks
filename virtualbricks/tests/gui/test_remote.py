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
The windows of another Virtualbricks: RemoteApplication, and what the
windows do differently over a connection. No window shows on the screen.
"""

import os

from twisted.internet import defer, task
from twisted.logger import LogLevel
from twisted.protocols import amp
from twisted.test import iosim

from virtualbricks import app
from virtualbricks.bricks import FakeProcess
from virtualbricks.config import images, settings
from virtualbricks.config.workspace import OpenProject
from virtualbricks.console import control
from virtualbricks.remote import client, follower, mirror
from virtualbricks.remote.client import Refused, RemoteEngine, Windows, start
from virtualbricks.remote.follower import LogKeeper
from virtualbricks.remote.mirror import MirrorFactory
from virtualbricks.tests import FakeLogger
from virtualbricks.tests.config.test_images import INFO, FakeQemuImg
from virtualbricks.tests.gui import (
    GuiTestCase,
    event,
    has_display,
    untranslated,
)
from virtualbricks.tests.remote.test_mirror import Project

if has_display:
    from gi.repository import Gtk

    from virtualbricks.gui import gui
    from virtualbricks.gui.dialogs.addimage import ExistingImageDialog
    from virtualbricks.gui.mainwindow import VBGUI, window
    from virtualbricks.gui.mainwindow.bricks.brickmenu import BrickActions
    from virtualbricks.gui.mainwindow.bricks.config.vm.disks import (
        DisksSection,
    )
    from virtualbricks.gui.mainwindow.images.imagemenu import ImageActions


class Reactor(task.Clock):
    """The clock of the windows; their shutdown triggers are only kept."""

    def __init__(self):
        super().__init__()
        self.triggers = []

    def addSystemEventTrigger(self, *args):
        self.triggers.append(args)


class Publisher:
    def __init__(self):
        self.observers = []

    def addObserver(self, observer):
        self.observers.append(observer)


class FakeGtkWindow:
    def __init__(self):
        self.destroyed = False

    def in_destruction(self):
        return self.destroyed

    def destroy(self):
        self.destroyed = True


class FakeWindows:
    """The main window, as RemoteApplication tells it."""

    def __init__(self, shown, engine, messages):
        self.engine = engine
        self.messages = messages
        self.window = FakeGtkWindow()
        self.calls = []
        self.reconnect = None
        shown.append(self)

    def set_title(self):
        self.calls.append(("title", window.remote_title(self.engine)))

    def connection_lost(self, text, reconnect):
        self.calls.append(("lost", text))
        self.reconnect = reconnect

    def reconnected(self):
        self.calls.append(("reconnected",))

    def on_opened(self):
        self.calls.append(("opened",))

    def on_quit(self, factory):
        self.calls.append(("quit",))


class RemoteTestCase(GuiTestCase):
    """A Virtualbricks there, on its factory; the windows of this test."""

    def setUp(self):
        super().setUp()
        untranslated(self)
        self.factory.runtime_dir = "/run/vb"
        self.patch(control, "logger", FakeLogger())
        self.patch(follower, "logger", FakeLogger())
        self.patch(mirror, "logger", FakeLogger())
        self.patch(amp, "_log", FakeLogger())
        self.logger = FakeLogger()
        self.patch(gui, "logger", self.logger)
        self.patch(gui, "globalLogPublisher", Publisher())
        self.manager.current = Project(self.folder("lab1"))
        settings.set_setting("workspace", self.manager.path)
        self.keeper = LogKeeper()
        self.patch(follower, "keeper", self.keeper)
        self.clock = task.Clock()
        self.server = control.ControlFactory(
            self.factory, self.clock, control.AMPControl
        )
        self.refusal = None
        self.connections = []
        self.patch(client, "connect", self.connect)
        self.shown = []
        self.patch(
            gui,
            "VBGUI",
            lambda engine, messages: FakeWindows(self.shown, engine, messages),
        )
        self.sw1 = self.factory.new_brick("switch", "sw1")
        # the machine there lacks nothing, unless a test says otherwise
        self.patch(follower.ksm, "check_ksm", lambda: True)
        self.patch(follower, "missing_programs", lambda vde, qemu: [])

    def connect(self, target, copy, reactor):
        """The connection to the Virtualbricks of the test, followed."""

        if self.refusal is not None:
            return defer.fail(Refused(self.refusal))
        windows, connection, pump = iosim.connectedServerAndClient(
            lambda: self.server.buildProtocol(None), lambda: Windows(copy)
        )
        self.connections.append((windows, connection, pump))
        started = defer.ensureDeferred(start(windows, target))
        pump.flush()
        return started.addCallback(lambda _: windows)

    def turn(self):
        """The end of the turn there, and what it sends."""

        self.clock.advance(0)
        for _windows, _connection, pump in self.connections:
            pump.flush()

    def launch(self, install_settings=None):
        """The windows of the Virtualbricks at /run/lab.amp, started."""

        config = app.Options()
        config.parseOptions(["--connect", "unix:/run/lab.amp"])
        application = gui.RemoteApplication(config)
        application.install_locale = lambda: None
        # the settings of the test, which both sides share
        application.install_settings = install_settings or (lambda: None)
        self.patch(application.logger, "start", lambda application: None)
        self.reactor = Reactor()
        self.done = application.run(self.reactor)
        return application


class TestRemoteApplication(RemoteTestCase):

    def test_the_windows(self):
        application = self.launch()
        [windows] = self.shown
        self.assertIsInstance(windows.engine, RemoteEngine)
        self.assertIs(windows.engine, application.engine)
        self.assertIs(windows.messages, application.messages)
        copy = windows.engine.factory
        self.assertIsInstance(copy, MirrorFactory)
        self.assertIsNotNone(copy.get_brick("sw1"))
        self.assertEqual(
            windows.calls,
            [("title", "Virtualbricks (project: lab1 on /run/lab.amp)")],
        )
        self.assertNoResult(self.done)
        self.assertEqual(
            self.reactor.triggers,
            [
                ("before", "shutdown", gui.store_settings),
                ("before", "shutdown", application.logger.stop),
            ],
        )
        self.assertEqual(self.logger.events, [])

    def test_it_cant_connect(self):
        self.refusal = "Can't reach /run/lab.amp: Connection refused"
        self.launch()
        self.assertEqual(self.shown, [])
        failure = self.failureResultOf(self.done, SystemExit)
        self.assertEqual(
            str(failure.value), "Can't reach /run/lab.amp: Connection refused"
        )

    def lacking(self):
        """The machine there lacks KSM and a program."""

        self.patch(follower.ksm, "check_ksm", lambda: False)
        self.patch(
            follower, "missing_programs", lambda vde, qemu: ["vde_switch"]
        )

    def test_the_warning_at_start(self):
        self.lacking()
        self.launch()
        self.assertEqual(self.logger.levels(), ["error"])
        [(_level, text, fields)] = self.logger.events
        self.assertEqual(text, window.components_not_found)
        self.assertEqual(
            fields["text"],
            window.ksm_not_found
            + "\n"
            + window.programs_not_found.format(programs="vde_switch"),
        )

    def test_no_warning(self):
        self.lacking()
        self.launch(
            lambda: settings.set_setting("warn_missing_programs", False)
        )
        self.assertEqual(self.logger.events, [])

    def test_the_messages_there(self):
        application = self.launch()
        self.keeper(event("sw1 started", LogLevel.warn))
        self.turn()
        [entry] = list(application.messages.entries)
        self.assertEqual(entry.source, "Project on /run/lab.amp")
        self.assertEqual(entry.level, "warn")
        self.assertEqual(entry.lines, ["sw1 started"])

    def test_a_project_opened_there(self):
        self.launch()
        [windows] = self.shown
        self.manager.opened.notify(self.manager)
        self.turn()
        self.assertEqual(windows.calls[-1], ("opened",))

    def test_lost_then_reconnect(self):
        application = self.launch()
        [windows] = self.shown
        first = application.engine.windows
        self.connections[0][1].transport.loseConnection()
        self.turn()
        kind, text = windows.calls[-1]
        self.assertEqual(kind, "lost")
        self.assertTrue(
            text.startswith("The connection to /run/lab.amp is lost: ")
        )
        self.factory.new_brick("switch", "sw2")
        windows.reconnect()
        self.turn()
        self.assertIsNot(application.engine.windows, first)
        self.assertEqual(windows.calls[-2:], [("opened",), ("reconnected",)])
        self.assertIsNotNone(application.copy.get_brick("sw2"))
        # the new connection, watched as the first
        self.keeper(event("sw2 started"))
        self.turn()
        self.assertEqual(len(application.messages.entries), 1)
        self.connections[1][1].transport.loseConnection()
        self.turn()
        self.assertEqual(windows.calls[-1][0], "lost")

    def test_reconnect_refused(self):
        self.launch()
        [windows] = self.shown
        self.connections[0][1].transport.loseConnection()
        self.turn()
        self.refusal = "Can't reach /run/lab.amp: Connection refused"
        windows.reconnect()
        self.assertEqual(
            windows.calls[-1],
            ("lost", "Can't reach /run/lab.amp: Connection refused"),
        )

    def test_it_quits_there(self):
        self.launch()
        [windows] = self.shown
        self.factory.quit()
        self.turn()
        self.connections[0][1].transport.loseConnection()
        self.turn()
        self.assertEqual(
            windows.calls[-1], ("lost", "Virtualbricks on /run/lab.amp quit")
        )
        # another Virtualbricks there, then the connection lost
        windows.reconnect()
        self.connections[1][1].transport.loseConnection()
        self.turn()
        self.assertIn("is lost", windows.calls[-1][1])

    def test_quit(self):
        application = self.launch()
        [windows] = self.shown
        self.successResultOf(application.engine.quit())
        self.turn()
        self.assertEqual(windows.calls[-1], ("quit",))
        self.assertTrue(windows.window.destroyed)
        self.assertIsNone(self.successResultOf(self.done))
        # the connection closes; the Virtualbricks there goes on
        self.assertFalse(application.engine.windows.connected)
        self.assertFalse(self.factory.quit_d.called)
        # quit again: nothing more
        application.quit()
        self.assertEqual(windows.calls.count(("quit",)), 1)


class TestTheTitle(GuiTestCase):

    def engine(self, project, **machine):
        copy = MirrorFactory(task.Clock())
        copy.project = project
        copy.settings = {"workspace": "/home/lab/.virtualbricks"}
        copy.machine = dict(
            {"workspace": "/home/lab/.virtualbricks"}, **machine
        )
        return RemoteEngine(copy, None, "lab.example")

    def test_titles(self):
        untranslated(self)
        self.assertEqual(
            window.remote_title(self.engine(None)),
            "Virtualbricks on lab.example",
        )
        self.assertEqual(
            window.remote_title(self.engine("ospf")),
            "Virtualbricks (project: ospf on lab.example)",
        )
        self.assertEqual(
            window.remote_title(self.engine("ospf", workspace="/labs")),
            "Virtualbricks (project: ospf, workspace: /labs on lab.example)",
        )


class TestTheMainWindow(GuiTestCase):
    """The main window over a connection, never shown."""

    def setUp(self):
        super().setUp()
        untranslated(self)
        settings.set_setting("tray_icon", False)
        self.patch(Gtk.Window, "show", lambda widget: None)
        self.copy = MirrorFactory(task.Clock())
        self.copy.project = "ospf"
        self.quits = []
        self.engine = RemoteEngine(
            self.copy, None, "lab", quit=lambda: self.quits.append(True)
        )
        self.gui = VBGUI(self.engine)
        self.addCleanup(self.gui.window.destroy)

    def test_the_title(self):
        self.gui.set_title()
        self.assertEqual(
            self.gui.window.get_title(),
            "Virtualbricks (project: ospf on lab)",
        )

    def test_import_and_export_wait(self):
        for item in (self.gui.import_item, self.gui.export_item):
            self.assertFalse(item.get_sensitive())
            self.assertEqual(
                item.get_tooltip_text(), "Not over a connection, for now"
            )

    def test_the_bar(self):
        self.assertFalse(self.gui.lost_bar.get_visible())
        tries = []
        self.gui.connection_lost("It is lost", lambda: tries.append(True))
        self.assertTrue(self.gui.lost_bar.get_visible())
        self.assertEqual(self.gui.lost_words.get_text(), "It is lost")
        self.assertFalse(self.gui.menubar.get_sensitive())
        self.assertFalse(self.gui.main_notebook.get_sensitive())
        self.gui.lost_bar.response(window.RECONNECT)
        self.assertEqual(tries, [True])
        self.gui.reconnected()
        self.assertFalse(self.gui.lost_bar.get_visible())
        self.assertTrue(self.gui.menubar.get_sensitive())
        self.assertTrue(self.gui.main_notebook.get_sensitive())
        self.gui.lost_bar.response(window.QUIT)
        self.assertEqual(self.quits, [True])


class NotHere:
    """The engine of windows over a connection, as the items see it."""

    local = False

    def __init__(self, factory):
        self.factory = factory


class FakeGui:
    def __init__(self, factory):
        self.brickfactory = factory
        self.engine = NotHere(factory)
        self.window = None


class TestWhatWaits(GuiTestCase):
    """What the windows grey over a connection: 19 R12, R13, step 6."""

    def setUp(self):
        super().setUp()
        untranslated(self)
        os.makedirs(self.factory.runtime_dir)
        self.manager.current = OpenProject(self.folder("lab1"), None)
        self.gui = FakeGui(self.factory)

    def enabled(self, actions):
        return {
            name
            for name in actions.list_actions()
            if actions.lookup_action(name).get_enabled()
        }

    def test_the_console_and_sigterm(self):
        vm = self.factory.new_brick("qemu", "vm1")
        vm.proc = FakeProcess(vm)
        enabled = self.enabled(BrickActions(self.gui, vm))
        self.assertNotIn("console", enabled)
        self.assertNotIn("terminate", enabled)
        self.assertIn("kill", enabled)

    def test_show_in_files(self):
        image = self.image("frr")
        self.assertNotIn("show", self.enabled(ImageActions(self.gui, image)))

    def test_the_menu_of_a_disk(self):
        image = self.image("frr")
        vm = self.factory.new_brick("qemu", "vm1")
        vm.update_config({"hda_image": "frr", "hda_private": True})
        with open(vm.disk("hda").get_cow_path(), "w"):
            pass
        qemu_img = FakeQemuImg()
        qemu_img.infos[image.path] = INFO
        section = DisksSection(vm, self.gui.engine, images.InfoCache(qemu_img))
        self.addCleanup(section.destroy)
        enabled = self.enabled(section.row("hda").actions)
        self.assertEqual(
            enabled & {"save", "merge", "start-over", "show"}, set()
        )
        self.assertIn("remove", enabled)

    def test_no_copy_of_a_file(self):
        path = os.path.join(self.folder("outside"), "frr.qcow2")
        with open(path, "wb") as file:
            file.write(b"disk")

        class Engine(NotHere):
            def image_info(self, path):
                return defer.succeed(images.parse_info(INFO))

        dialog = ExistingImageDialog(Engine(self.factory))
        self.addCleanup(dialog.dialog.destroy)
        dialog.choose(path)
        self.assertTrue(dialog.in_place_radio.get_active())
        self.assertFalse(dialog.copy_radio.get_sensitive())
        self.assertIn("No copy over a connection", dialog.copy_note.get_text())
        self.assertFalse(dialog.copies())
